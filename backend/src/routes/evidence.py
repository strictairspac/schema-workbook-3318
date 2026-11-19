from fastapi import APIRouter,Depends
from src.config.database import db_session
from src.utils.security import current,writer
from src.schemas.evidence import SampleInput,SampleCorrection,PackageInput
from src.services import samples,evidence
import json
from fastapi.responses import Response
router=APIRouter()
@router.get('/samples')
def list_samples(db=Depends(db_session),user=Depends(current)):return samples.listing(db)
@router.post('/samples',status_code=201)
def create_sample(data:SampleInput,db=Depends(db_session),user=Depends(writer)):return samples.create(db,data,user)
@router.get('/samples/{ident}')
def get_sample(ident:int,db=Depends(db_session),user=Depends(current)):return samples.detail(db,ident)
@router.get('/samples/{ident}/revisions')
def list_revisions(ident:int,db=Depends(db_session),user=Depends(current)):return samples.revisions(db,ident)
@router.put('/samples/{ident}')
def correct_sample(ident:int,data:SampleCorrection,db=Depends(db_session),user=Depends(writer)):return samples.correct(db,ident,data,user)
@router.get('/packages')
def list_packages(db=Depends(db_session),user=Depends(current)):return evidence.listing(db)
@router.post('/packages',status_code=201)
def create_package(data:PackageInput,db=Depends(db_session),user=Depends(writer)):return evidence.create(db,data,user)
@router.get('/packages/{ident}')
def get_package(ident:int,db=Depends(db_session),user=Depends(current)):return evidence.detail(db,ident)
@router.post('/packages/{ident}/publish')
def publish_package(ident:int,db=Depends(db_session),user=Depends(writer)):return evidence.publish(db,ident,user)
@router.get('/samples/{ident}/history')
def sample_history(ident:int,db=Depends(db_session),user=Depends(current)):return evidence.history(db,ident)
@router.get('/packages/{ident}/export')
def export_package(ident:int,db=Depends(db_session),user=Depends(current)):
    return Response(json.dumps(evidence.detail(db,ident),ensure_ascii=False,indent=2),media_type='application/json',headers={'Content-Disposition':f'attachment; filename="evidence-{ident}.json"'})
