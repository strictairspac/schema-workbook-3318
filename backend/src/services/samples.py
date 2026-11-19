from sqlalchemy import select
from fastapi import HTTPException
from src.models.entities import SampleBatch,SampleRevision,Relation,Audit
from src.utils.serialization import record
from .common import save
def _validate_rows(relation,columns,rows):
    if set(columns)!=set(relation.attributes):raise HTTPException(422,'样本列必须与关系的属性集合一致')
    if len(columns)!=len(set(columns)):raise HTTPException(422,'样本列不能重复')
    for offset,row in enumerate(rows,1):
        if set(row)!=set(columns):raise HTTPException(422,f'第 {offset} 行的字段必须与样本列完全一致')
        if not all(isinstance(v,(str,int,float)) or v is None for v in row.values()):raise HTTPException(422,f'第 {offset} 行含不支持的值')
def listing(db):return [record(x) for x in db.scalars(select(SampleBatch).order_by(SampleBatch.id))]
def detail(db,ident,batch=None):
    obj=batch or db.get(SampleBatch,ident)
    if not obj:raise HTTPException(404,'样本不存在')
    return record(obj)
def revisions(db,ident):
    if not db.get(SampleBatch,ident):raise HTTPException(404,'样本不存在')
    return [record(x) for x in db.scalars(select(SampleRevision).where(SampleRevision.batch_id==ident).order_by(SampleRevision.version.desc()))]
def create(db,data,user):
    relation=db.get(Relation,data.relation_id)
    if not relation:raise HTTPException(404,'关系不存在')
    _validate_rows(relation,data.columns,data.rows)
    obj=SampleBatch(code=data.code,relation_id=data.relation_id,columns=data.columns,rows=data.rows,version=1)
    db.add(obj);db.flush()
    db.add(SampleRevision(batch_id=obj.id,version=1,columns=data.columns,rows=data.rows,note=data.note))
    return save(db,obj,user,'登记抽检样本 '+data.code)
def correct(db,ident,data,user):
    obj=db.get(SampleBatch,ident)
    if not obj:raise HTTPException(404,'样本不存在')
    relation=db.get(Relation,obj.relation_id)
    if not relation:raise HTTPException(404,'关系不存在')
    _validate_rows(relation,obj.columns,data.rows)
    obj.rows=data.rows;obj.version=obj.version+1
    db.add(SampleRevision(batch_id=obj.id,version=obj.version,columns=obj.columns,rows=data.rows,note=data.note))
    db.flush()
    from src.services.evidence import invalidate_for_batch
    invalidate_for_batch(db,obj.id,f'样本已更正至 v{obj.version}')
    db.add(Audit(actor=user.email,action=f'更正抽检样本 {obj.code} 至 v{obj.version}'))
    db.commit()
    return record(obj)
def snapshot_rows(db,batch_id,version):
    """按版本取冻结样本；当前版本直接取活行，历史版本取修订记录。"""
    batch=db.get(SampleBatch,batch_id)
    if not batch:return None
    if batch.version==version:return {'columns':batch.columns,'rows':batch.rows,'current':True}
    revision=db.scalar(select(SampleRevision).where(SampleRevision.batch_id==batch_id,SampleRevision.version==version))
    if not revision:return None
    return {'columns':revision.columns,'rows':revision.rows,'current':False}
