"""``_parse_sort`` 跨表取列回归测试（2026-08-05 P0）。

事故：旧实现从列名映射里取「字典第一个非空列」，``main_net_inflow``
永远返回 ``IndividualFundFlow`` 的列 → ``/fund-flow/sector`` 默认排序
必 500（missing FROM-clause entry for table "individual_fund_flow"）。
修复后必须按调用方传入的 model 解析列，未知列兜底本表 trade_date。
"""

from app.models.fund_flow import (
    EtfFundFlow,
    FlowSignal,
    IndividualFundFlow,
    SectorFundFlow,
)
from app.services.fund_flow_service import _parse_sort


class TestParseSortModelResolution:
    def test_main_net_inflow_resolves_to_caller_model(self):
        col, direction = _parse_sort("-main_net_inflow", "main_net_inflow", model=SectorFundFlow)
        assert col is SectorFundFlow.main_net_inflow
        assert direction == "desc"

        col, _ = _parse_sort("main_net_inflow", "main_net_inflow", model=IndividualFundFlow)
        assert col is IndividualFundFlow.main_net_inflow

        col, _ = _parse_sort("-main_net_inflow", "main_net_inflow", model=FlowSignal)
        assert col is FlowSignal.main_net_inflow

    def test_ts_code_resolves_per_model(self):
        col, _ = _parse_sort("ts_code", "main_net_inflow", model=EtfFundFlow)
        assert col is EtfFundFlow.ts_code

    def test_column_not_on_model_falls_back_to_model_trade_date(self):
        # premium_rate 只有 EtfFundFlow 有；sector 查它要兜底本表 trade_date，
        # 绝不能返回 EtfFundFlow 的列（跨表 → UndefinedTable 500）
        col, direction = _parse_sort("-premium_rate", "main_net_inflow", model=SectorFundFlow)
        assert col is SectorFundFlow.trade_date
        assert direction == "desc"

    def test_unknown_column_falls_back_to_model_trade_date(self):
        col, direction = _parse_sort("-nonexistent", "main_net_inflow", model=FlowSignal)
        assert col is FlowSignal.trade_date
        assert direction == "desc"

    def test_empty_sort_uses_default_col_on_caller_model(self):
        col, direction = _parse_sort("", "inferred_net_inflow", model=EtfFundFlow)
        assert col is EtfFundFlow.inferred_net_inflow
        assert direction == "desc"

    def test_etf_only_columns_still_work_for_etf(self):
        col, _ = _parse_sort("-premium_rate", "inferred_net_inflow", model=EtfFundFlow)
        assert col is EtfFundFlow.premium_rate
