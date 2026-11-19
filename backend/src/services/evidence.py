from sqlalchemy import select
from redis import Redis
from fastapi import HTTPException
from src.models.entities import EvidencePackage,Relation,Dependency,Audit
from src.config.settings import REDIS_URL
from src.utils.serialization import record
from src.services.evidence_engine import rules_fingerprint
from src.services import samples
from .common import save
queue=Redis.from_url(REDIS_URL,decode_responses=True)
QUEUE_KEY='schemaworkbook:evidence-queue'
LIVE_STATES=('queued','running','review')
def listing(db):
    rows=[record(x) for x in db.scalars(select(EvidencePackage).order_by(EvidencePackage.id.desc()))]
    for item in rows:
        obj=db.get(EvidencePackage,item['id'])
        if refresh_stale(db,obj):item.update({'stale':obj.stale,'stale_reason':obj.stale_reason})
    return rows
def _current_rules(db,relation):
    deps=[{'lhs':x.lhs,'rhs':x.rhs} for x in db.scalars(select(Dependency).where(Dependency.relation_id==relation.id).order_by(Dependency.id))]
    return relation,deps,rules_fingerprint(relation.attributes,deps)
def create(db,data,user):
    batch=db.get(samples.SampleBatch,data.batch_id)
    if not batch:raise HTTPException(404,'样本不存在')
    relation=db.get(Relation,batch.relation_id)
    if not relation:raise HTTPException(404,'关系不存在')
    relation,deps,fingerprint=_current_rules(db,relation)
    # 同一样本、同一规则、同一行数上限的未出结果包直接复用，重试不会重复入队/发布。
    for existing in db.scalars(select(EvidencePackage).where(EvidencePackage.batch_id==batch.id,EvidencePackage.status.in_(LIVE_STATES))):
        if existing.rules_fingerprint==fingerprint and existing.row_limit==data.row_limit and existing.sample_version==batch.version:
            return record(existing)
    snapshot={'relation':record(relation),'dependencies':deps,'rules_fingerprint':fingerprint,'sample':{'id':batch.id,'code':batch.code,'version':batch.version,'columns':batch.columns,'rows':batch.rows}}
    obj=EvidencePackage(name=data.name,relation_id=relation.id,batch_id=batch.id,status='queued',rules_fingerprint=fingerprint,sample_version=batch.version,row_limit=data.row_limit,input_snapshot=snapshot)
    result=save(db,obj,user,'取证包入队 '+data.name)
    try:queue.rpush(QUEUE_KEY,str(obj.id))
    except Exception:
        obj.status='failed';obj.error='队列暂时不可用，请重试';db.commit();raise HTTPException(503,obj.error)
    return result
def get(db,ident):
    obj=db.get(EvidencePackage,ident)
    if not obj:raise HTTPException(404,'取证包不存在')
    return obj
def detail(db,ident):
    obj=get(db,ident);refresh_stale(db,obj);return record(obj)
def refresh_stale(db,obj):
    """草案规则或源数据变化时让包失效。

    样本被更正后版本递增：旧版本包不再代表当前样本，因此失效。
    已发布的包即使失效，仍保留全部输入快照，可按旧版查证（见 history/detail）。
    """
    if obj.status not in ('queued','running','review','published') or obj.stale:return obj
    reasons=[]
    relation=db.get(Relation,obj.relation_id)
    if not relation or _current_rules(db,relation)[2]!=obj.rules_fingerprint:reasons.append('草案规则已变化')
    old=samples.snapshot_rows(db,obj.batch_id,obj.sample_version)
    batch=db.get(samples.SampleBatch,obj.batch_id)
    current=samples.snapshot_rows(db,obj.batch_id,batch.version) if batch else None
    if old is None:reasons.append('样本原版本已不可回溯')
    elif current and (current['rows']!=old['rows'] or current['columns']!=old['columns']):reasons.append(f'样本已更正至 v{batch.version}')
    if reasons:
        obj.stale=True;obj.stale_reason='；'.join(reasons);db.commit();return obj
    return None
def invalidate_for_batch(db,batch_id,reason):
    """样本被更正后，让该样本所有未发布包立即失效，避免按过期样本发布。"""
    for obj in db.scalars(select(EvidencePackage).where(EvidencePackage.batch_id==batch_id)):
        if obj.status in ('queued','running','review'):
            obj.status='invalid';obj.stale=True;obj.stale_reason=reason
        elif obj.status=='published' and not obj.stale:
            obj.stale=True;obj.stale_reason=reason
    db.commit()
def publish(db,ident,user):
    obj=get(db,ident);refresh_stale(db,obj)
    if obj.status=='published' and not obj.stale:return record(obj)
    if obj.stale:raise HTTPException(409,'取证包已失效：'+obj.stale_reason+'。请按当前样本与规则重新生成。')
    if obj.status!='review':raise HTTPException(409,'只有待核对且已证明最少行数的取证包才能发布')
    if not obj.result or not obj.result.get('minimal') or obj.result.get('infeasible'):raise HTTPException(409,'取证包未证明最少行数，不能发布')
    from datetime import datetime,timezone
    obj.status='published';obj.published_at=datetime.now(timezone.utc)
    db.add(Audit(actor=user.email,action=f'发布取证包 {obj.name}'));db.commit()
    return record(obj)
def history(db,batch_id):
    """按旧版快照查证：该样本历史上已发布的取证包（含已失效版本）。"""
    rows=db.scalars(select(EvidencePackage).where(EvidencePackage.batch_id==batch_id).order_by(EvidencePackage.id.desc()))
    return [record(x) for x in rows if x.status=='published' or x.stale]
