from pydantic import BaseModel,Field,field_validator
class SampleInput(BaseModel):
    code:str=Field(min_length=2,max_length=80)
    relation_id:int=Field(gt=0)
    columns:list[str]=Field(min_length=1,max_length=10)
    rows:list[dict]=Field(min_length=1,max_length=60)
    note:str=Field(default='',max_length=300)
    @field_validator('columns')
    @classmethod
    def columns_valid(cls,v):
        if len(set(v))!=len(v) or any(not x.strip() or len(x)>40 for x in v):raise ValueError('样本列名必须唯一且非空，每项不超过40字')
        return v
class SampleCorrection(BaseModel):
    rows:list[dict]=Field(min_length=1,max_length=60)
    note:str=Field(default='',max_length=300)
class PackageInput(BaseModel):
    name:str=Field(min_length=2,max_length=120)
    batch_id:int=Field(gt=0)
    row_limit:int=Field(ge=2,le=60)
