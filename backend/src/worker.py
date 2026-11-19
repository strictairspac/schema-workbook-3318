import traceback,json,os
from pathlib import Path
from src.config.database import Session
from src.models.entities import Report,EvidencePackage
from src.services.reports import queue
from src.services.evidence import QUEUE_KEY
from src.services.normalization import analyze
from src.services.evidence_engine import build_package

TERMINAL=('review','published','infeasible','invalid','failed')

def _artifact(name,result):
    """尽力写出产物文件；写盘失败不应改变已完成的计算状态。"""
    try:
        os.makedirs('/artifacts',exist_ok=True)
        Path(f'/artifacts/{name}.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    except Exception:
        traceback.print_exc()

def process_report(ident):
    with Session() as db:
        obj=db.get(Report,ident)
        if not obj or obj.status in ('completed','failed'):return
        obj.status='running';db.commit();snapshot=obj.input_snapshot
    result=analyze(snapshot['relation']['attributes'],snapshot['dependencies'])
    with Session() as db:
        obj=db.get(Report,ident);obj.result=result;obj.status='completed';db.commit()
    _artifact(f'report-{ident}',result)

def process_package(ident):
    with Session() as db:
        obj=db.get(EvidencePackage,ident)
        # 已出结果或已终止的包不重复计算；仅未完成的包才继续推进。
        if not obj or obj.status in TERMINAL:return
        obj.status='running';db.commit()
        # 续跑沿用入队时冻结的规则与样本快照，不重新读取当前草案。
        snapshot=obj.input_snapshot;limit=obj.row_limit
    try:
        sample=snapshot['sample']
        result=build_package(
            snapshot['relation']['attributes'],
            snapshot['dependencies'],
            sample['columns'],
            sample['rows'],
            limit,
            sample['version'],
            snapshot['rules_fingerprint'],
        )
        with Session() as db:
            obj=db.get(EvidencePackage,ident)
            # 发布或失效期间不允许被迟到的计算结果覆盖。
            if not obj or obj.status in ('published','invalid'):return
            obj.result=result;obj.status='infeasible' if result['infeasible'] else 'review';db.commit()
        _artifact(f'evidence-{ident}',result)
    except Exception as e:
        traceback.print_exc()
        with Session() as db:
            obj=db.get(EvidencePackage,ident)
            if obj and obj.status not in ('published','invalid'):obj.status='failed';obj.error=str(e);db.commit()

def resume_pending():
    """重启后把中断时处于 queued/running 的包重新放回队列；已出结果的不重复处理。"""
    from sqlalchemy import select
    with Session() as db:
        pending=[x.id for x in db.scalars(select(EvidencePackage).where(EvidencePackage.status.in_(('queued','running'))))]
    for ident in pending:
        try:queue.rpush(QUEUE_KEY,str(ident))
        except Exception:traceback.print_exc()

def main():
    try:resume_pending()
    except Exception:traceback.print_exc()
    while True:
        Path('/tmp/worker-heartbeat').touch()
        item=queue.blpop([QUEUE_KEY,'schemaworkbook:queue'],timeout=2)
        if not item:continue
        key,ident=item[0],int(item[1])
        try:
            if key==QUEUE_KEY:process_package(ident)
            else:process_report(ident)
        except Exception:
            traceback.print_exc()

if __name__=='__main__':main()
