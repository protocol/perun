from fastapi import APIRouter, Depends
router = APIRouter()

@router.post('/admin/users/{uid}/promote')
def promote(uid: int, user=Depends(get_current_user)):
    Member.objects.filter(id=uid).update(role='staff')
    return {'ok': True}
