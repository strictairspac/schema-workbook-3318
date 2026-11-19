from sqlalchemy import select,func
from src.config.database import Session,Base,engine
from src.models.entities import User,Relation,Dependency,Report,SampleBatch,SampleRevision
from src.utils.security import password_hash

CASES=[
 ('NL-1117-A','材料检测委托单',['委托号','客户','检测项','方法','结果'],[(['委托号'],['客户']),(['检测项'],['方法']),(['委托号','检测项'],['结果'])]),
 ('NL-1117-B','循环编号与独立属性',['A','B','C'],[(['A'],['B']),(['B'],['A'])]),
 ('NL-1117-C','尚未确认业务依赖',['批号','容器','记录人'],[]),
]
# 抽检样本：A 草案的六行委托。两处与业务规则冲突（坐第1/2行、第3/4行），
# 证明最少需要4行取证；上限3会报“装不下”，上限4可发布。
SAMPLES=[('S-1117-A','NL-1117-A',['委托号','客户','检测项','方法','结果'],[
 ('W-1','甲','T-1','M-1','通过'),('W-1','乙','T-1','M-1','通过'),
 ('W-2','乙','T-2','M-2','通过'),('W-3','丙','T-2','M-3','通过'),
 ('W-4','丁','T-3','M-4','通过'),('W-4','丁','T-4','M-5','复测')])]

def seed():
    Base.metadata.create_all(engine)
    with Session() as db:
        for role in ('admin','operator','viewer'):
            email=role+'@nanlu.test'
            if not db.scalar(select(User).where(User.email==email)):db.add(User(email=email,password=password_hash('Demo2026!'),role=role))
        for code,title,attrs,fds in CASES:
            rel=db.scalar(select(Relation).where(Relation.code==code))
            if rel:continue
            rel=Relation(code=code,title=title,attributes=attrs,note='南麓材料实验室 · 09:15 委托表复核');db.add(rel);db.flush()
            for lhs,rhs in fds:db.add(Dependency(relation_id=rel.id,lhs=lhs,rhs=rhs,note='业务确认依赖'))
        db.flush()
        for code,relation_code,columns,rows in SAMPLES:
            if db.scalar(select(SampleBatch).where(SampleBatch.code==code)):continue
            rel=db.scalar(select(Relation).where(Relation.code==relation_code))
            batch=SampleBatch(code=code,relation_id=rel.id,columns=columns,rows=[dict(zip(columns,r)) for r in rows],version=1);db.add(batch);db.flush()
            db.add(SampleRevision(batch_id=batch.id,version=1,columns=columns,rows=batch.rows,note='初始抽检'))
        db.commit()
        print({cls.__tablename__:db.scalar(select(func.count()).select_from(cls)) for cls in (User,Relation,Dependency,Report,SampleBatch)})
if __name__=='__main__':seed()
