from fastapi import APIRouter, Depends

from resume_ai.services.health_service import HealthService

router = APIRouter(prefix="/health", tags=["Health"])


def get_health_service() -> HealthService:
    return HealthService()


@router.get("")
async def health_check(service: HealthService = Depends(get_health_service)):
    return service.status()
