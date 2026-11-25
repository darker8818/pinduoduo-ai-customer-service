"""Run an actual client rule with synthetic data only."""
from client.green.aftersale52 import answer

if __name__ == "__main__":
    order = {"goods_name": "示例玫瑰", "order_status_str": "未发货",
             "after_sales_status_str": "退款成功"}
    print(answer("我要退货", "verified", order))
