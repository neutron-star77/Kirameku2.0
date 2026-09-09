"""公共依赖 — 统一从这里导入 get_session / get_current_user / require_admin"""

from app.database import get_session
from app.utils.auth import get_current_user, require_admin

__all__ = ["get_session", "get_current_user", "require_admin"]
