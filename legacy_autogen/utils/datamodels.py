from typing import List
from pydantic import BaseModel

class CustomBaseModel(BaseModel):
    class Config:
        arbitrary_types_allowed = True


class SignalModel(CustomBaseModel):
    BuySignal: List[bool]
    SellSignal: List[bool]
    Description: str


class BacktestPerformanceMetrics(CustomBaseModel):
    cumulative_return: str
    cagr: str
    mdd: str
    sharpe_ratio: str


class WorkFlowTasks(BaseModel):
    stock_idea_task_description: str
    investment_analysis_instructions: str
    stock_report_task_instructions: str