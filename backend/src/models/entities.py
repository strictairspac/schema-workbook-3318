from sqlalchemy import Column,Integer,String,JSON,DateTime,ForeignKey,Text,Boolean
from datetime import datetime,timezone
from src.config.database import Base
class User(Base):
    __tablename__='users'
    id=Column(Integer,primary_key=True);email=Column(String(120),unique=True,nullable=False);password=Column(String(300),nullable=False);role=Column(String(20),nullable=False)
class Relation(Base):
    __tablename__='relations'
    id=Column(Integer,primary_key=True);code=Column(String(80),unique=True,nullable=False);title=Column(String(160),nullable=False);attributes=Column(JSON,nullable=False);note=Column(String(300),default='')
class Dependency(Base):
    __tablename__='dependencies'
    id=Column(Integer,primary_key=True);relation_id=Column(Integer,ForeignKey('relations.id'),nullable=False);lhs=Column(JSON,nullable=False);rhs=Column(JSON,nullable=False);note=Column(String(300),default='')
class Report(Base):
    __tablename__='reports'
    id=Column(Integer,primary_key=True);name=Column(String(120),nullable=False);relation_id=Column(Integer,ForeignKey('relations.id'),nullable=False)
    status=Column(String(20),nullable=False,default='queued');input_snapshot=Column(JSON,nullable=False);result=Column(JSON,nullable=True);error=Column(Text,nullable=True)
    created_at=Column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))
class SampleBatch(Base):
    """抽检样本：一批原始行，可按核对结果更正，每次更正生成新版本。"""
    __tablename__='sample_batches'
    id=Column(Integer,primary_key=True);code=Column(String(80),unique=True,nullable=False)
    relation_id=Column(Integer,ForeignKey('relations.id'),nullable=False)
    columns=Column(JSON,nullable=False);rows=Column(JSON,nullable=False)
    version=Column(Integer,nullable=False,default=1)
    created_at=Column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))
class SampleRevision(Base):
    """样本历史版本，仅追加；旧版取证包据此按原版本查证。"""
    __tablename__='sample_revisions'
    id=Column(Integer,primary_key=True);batch_id=Column(Integer,ForeignKey('sample_batches.id'),nullable=False)
    version=Column(Integer,nullable=False);columns=Column(JSON,nullable=False);rows=Column(JSON,nullable=False)
    note=Column(String(300),default='');created_at=Column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))
class EvidencePackage(Base):
    """取证包：按草案规则与行数上限，给出能推翻整批样本中每条依赖的最少原始行。"""
    __tablename__='evidence_packages'
    id=Column(Integer,primary_key=True);name=Column(String(120),nullable=False)
    relation_id=Column(Integer,ForeignKey('relations.id'),nullable=False)
    batch_id=Column(Integer,ForeignKey('sample_batches.id'),nullable=False)
    status=Column(String(20),nullable=False,default='queued')
    rules_fingerprint=Column(String(64),nullable=False)
    sample_version=Column(Integer,nullable=False,default=1)
    row_limit=Column(Integer,nullable=False,default=50)
    input_snapshot=Column(JSON,nullable=False);result=Column(JSON,nullable=True);error=Column(Text,nullable=True)
    stale=Column(Boolean,nullable=False,default=False);stale_reason=Column(String(300),default='')
    published_at=Column(DateTime(timezone=True),nullable=True)
    created_at=Column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))
class Audit(Base):
    __tablename__='audit_logs'
    id=Column(Integer,primary_key=True);actor=Column(String(120),nullable=False);action=Column(String(160),nullable=False);created_at=Column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))
