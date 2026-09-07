# canonkeeper 事实级查全评测

- 时间：2026-09-08T00:52:28+08:00
- provider：deepseek · 标注：bench-v1.yaml

| 章 | number | entity | attr | change | event | relation | time | 信号(signal) |
|---|---|---|---|---|---|---|---|---|
| 艾尔德兰 第1章 | 13/15 | 6/7 | 2/4 | 1/2 | 5/7 | — | 1/1 | 1/1 |
| 艾尔德兰 第2章 | 12/12 | 5/6 | 1/1 | 1/1 | 3/5 | — | 0/1 | 1/1 |
| 艾尔德兰 第3章 | 8/8 | 2/2 | — | 0/1 | 2/3 | — | — | 1/1 |
| 没钱修什么仙 第1章 | 10/22 | 8/10 | 0/3 | 0/1 | 3/6 | 0/1 | 0/1 | 1/2 |

## 分品类总查全

| 品类 | 查全 |
|---|---|
| number | 43/57 = 75% |
| entity | 21/25 = 84% |
| attr | 3/8 = 38% |
| change | 2/5 = 40% |
| event | 13/21 = 62% |
| relation | 0/1 = 0% |
| time | 1/3 = 33% |
| signal | 4/5 = 80% |

## 漏报明细

### 艾尔德兰 第1章
- [number] n01: 全服广播登出队列人数
- [number] n04: 豆包分析耗时
- [entity] e07: 酒馆
- [attr] a02: 46
- [attr] a04: 21
- [change] c02: 50→46
- [event] v01: 全服广播登出队列
- [event] v04: 匿名警告邮件

### 艾尔德兰 第2章
- [entity] e05: 北边废矿
- [event] v02: None
- [event] v05: 500金币六人平分邀请
- [time] t01: 第1章第三天晚上→本章次日（「昨天的46次已清零」）

### 艾尔德兰 第3章
- [change] c01: None
- [event] v02: 200金币到账

### 没钱修什么仙 第1章
- [number] n01: 嵩阳市学生日均睡眠
- [number] n02: 张羽睡眠时长
- [number] n03: 九年差距
- [number] n04: 入读小学年龄
- [number] n05: 入高中年龄
- [number] n06: 牛妖补剂日发量
- [number] n07: 补剂修炼效果
- [number] n08: 后备金
- [number] n13: 炼气突破筑基法力要求
- [number] n14: 炼气法力上限
- [number] n15: 仙道科目总分
- [number] n16: 通识科总分
- [entity] e05: 嵩阳市
- [entity] e07: 掌心符号
- [attr] a01: 地上三十六层
- [attr] a02: 高一总分第一
- [attr] a03: 七十多万
- [change] c03: 汇总负债
- [event] v04: 500块
- [event] v05: 逾期电话与短信
- [event] v06: 两人翻借贷流水
- [relation] r01: None
- [time] t01: 「穿越异世界才第一天」

