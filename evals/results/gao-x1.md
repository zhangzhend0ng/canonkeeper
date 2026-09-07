# canonkeeper 事实级查全评测

- 时间：2026-09-08T01:33:51+08:00
- provider：deepseek · 标注：bench-v1.yaml

| 章 | number | entity | attr | change | event | relation | time | 信号(signal) |
|---|---|---|---|---|---|---|---|---|
| 艾尔德兰 第1章 | 12/15 | 7/7 | 2/4 | 2/2 | 5/7 | — | 1/1 | 1/1 |
| 艾尔德兰 第2章 | 11/12 | 6/6 | 1/1 | 1/1 | 1/5 | — | 0/1 | 1/1 |
| 艾尔德兰 第3章 | 7/8 | 2/2 | — | 0/1 | 2/3 | — | — | 1/1 |
| 没钱修什么仙 第1章 | 4/22 | 10/10 | 0/3 | 0/1 | 4/6 | 0/1 | 0/1 | 1/2 |

## 分品类总查全

| 品类 | 查全 |
|---|---|
| number | 34/57 = 60% |
| entity | 25/25 = 100% |
| attr | 3/8 = 38% |
| change | 3/5 = 60% |
| event | 12/21 = 57% |
| relation | 0/1 = 0% |
| time | 1/3 = 33% |
| signal | 4/5 = 80% |

## 漏报明细

### 艾尔德兰 第1章
- [number] n09: 药水材料成本
- [number] n11: 制作与售出数量
- [number] n12: 售罄时长
- [attr] a02: 46
- [attr] a04: 21
- [event] v01: 全服广播登出队列
- [event] v03: 酒馆床位3金币一晚

### 艾尔德兰 第2章
- [number] n02: 文中自报剩余（与50-4=46矛盾，疑似源稿不一致）
- [event] v01: None
- [event] v02: None
- [event] v04: 副本失败
- [event] v05: 500金币六人平分邀请
- [time] t01: 第1章第三天晚上→本章次日（「昨天的46次已清零」）

### 艾尔德兰 第3章
- [number] n07: 技能循环周期
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
- [number] n09: 母亲转账
- [number] n10: 租借天灵根花费
- [number] n13: 炼气突破筑基法力要求
- [number] n14: 炼气法力上限
- [number] n15: 仙道科目总分
- [number] n16: 通识科总分
- [number] n18: 距月考时间
- [number] n19: 昆墟地上层数
- [number] n20: 昆墟地下层数
- [number] n22: 白真真债务
- [attr] a01: 地上三十六层
- [attr] a02: 高一总分第一
- [attr] a03: 七十多万
- [change] c03: 汇总负债
- [event] v05: 逾期电话与短信
- [event] v06: 两人翻借贷流水
- [relation] r01: None
- [time] t01: 「穿越异世界才第一天」

