"""Data API access log — X-API-Key 通道的访问审计（2026-11-04）。

外部只读数据消费方（见 app/api/deps.py::_authenticate_data_api_key）的
每一次请求落一行；管理后台聚合展示。best-effort 写入：审计失败绝不
影响业务响应。
"""

from sqlalchemy import Column, DateTime, Integer, String, func

from app.core.database import Base


class DataApiAccessLog(Base):
    __tablename__ = "data_api_access_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now(), index=True)
    username = Column(String(50), nullable=False, comment="API key 映射的服务账号")
    method = Column(String(10), nullable=False)
    path = Column(String(255), nullable=False, index=True)
    status_code = Column(Integer, nullable=False)
    duration_ms = Column(Integer, nullable=True)
    client_ip = Column(String(64), nullable=True)
    user_agent = Column(String(255), nullable=True)
