# 多级供应链鲁棒库存研究

基于有限提前期情景的多级保证服务库存研究。此公开版本包括研究工作稿、静态鲁棒混合整数规划原型和十进制物料流模拟器。项目仍在探索阶段，论文尚不具备投稿条件。

## 研究范围

研究工作稿使用 Willems 案例 01 作为网络结构基准，并将不同来源的销售或订单序列分别映射到末端需求。它们并非同一企业的数据。现有评价期已有探索接触，不能视为盲测；模型目标也不等同于真实成本或服务改善。文稿中的 [E...] 是本地研究证据编号；由于数据及部分材料的公开许可尚待核实，这些内部证据未随仓库发布，文稿结果目前无法仅凭本仓库完整复现。

本仓库中的鲁棒求解器由案例 01 工程实现改写为接收自定义有向无环网络；演示网络和全部参数均为虚构，不包含 Willems 数据。公开版尚未证明对任意网络的论文结论或实证结果成立。

## 安装与示例

需要 Python 3.10+。在仓库根目录运行：

~~~bash
python -m pip install .
python -m inventory_lab.robust_demo
python -m inventory_lab.flow_demo --output outputs/flow_demo.json
python examples/read_flow_result.py --input outputs/flow_demo.json
python -m unittest discover -s tests -v
python -m unittest discover -s examples -p test_read_flow_result.py -v
~~~

物料流演示不会覆盖已有输出；重复运行时请更换输出文件名。演示提供虚构的供应与订单信息，不是现实运营测算。

## 结构

- paper/主论文工作稿.md：带局限性说明的研究工作稿。
- inventory_lab/robust.py：有限情景、共享整数服务时间的极小极大模型；网络、需求缓冲曲线、情景和权重由输入提供。
- inventory_lab/robust_demo.py：可运行的虚构网络示例。
- inventory_lab/flow*.py：独立的离散时间物料流模拟与演示。
- tests/：合成实例验证；鲁棒示例还与独立枚举比较。
- examples/：模拟结果阅读工具及测试。

## 数据与许可

本仓库不分发第三方原始数据、订单明细、派生明细、案例原始工作簿或未经核实的案例拓扑参数。Willems 数据原始来源见 [Willems (2008)](https://doi.org/10.1287/msom.1070.0176)；其他数据来源、使用限制和参考文献见工作稿。获取与再分发须分别遵循各来源的条件。

本仓库尚未确定代码和论文的开源许可证；公开可见不等于授予再使用许可。
