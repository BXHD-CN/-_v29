# 首页视觉 V3：极光科技风（复刻“莱茵科技”类艺术效果）

> 需求：首页更好看，复刻“莱茵科技”的艺术效果；用 JS / ReAct 迭代方式完成。
> 说明：公开渠道未能访问到“莱茵科技”的具体官网（ZCool 作品页被 WAF 拦截、福州莱茵科技官网为模板建站），因此按“深空极光 + 精密网格 + 玻璃质感 + 流动数据”的科技艺术方向实现；若提供参考链接可再逐项对齐。

## 1. 视觉构成

| 层 | 实现 | 文件 |
| --- | --- | --- |
| 极光背景 | WebGL 片元着色器：fbm 噪声流动 + 鼠标光斑 + 暗角 + 颗粒；WebGL 不可用时降级为 CSS 多径向渐变（hero-aura），保证任何环境都有色彩 | `static/js/aurora.js` |
| 精密网格 | 72px 网格 + 径向遮罩，仅在 Hero 顶部可见，营造“仪表盘”感 | home.css |
| 光环轨道 | 三层旋转轨道（含发光粒子），反向旋转的虚线环 | home.css |
| 标题动效 | 两行大字 + 渐变流光（#67E8F9→#A5B4FC→#F0ABFC），逐行入场 | home.css / home.js |
| 数据卡 | 玻璃拟态（backdrop-filter + 细边框 + 内发光），数字滚动计数 | home.css / home.js |
| 跑马灯 | 数据来源/能力标签横向流动，悬停暂停 | home.css / home.js |
| 知识图 | Canvas 2D 伪 3D：透视投影 + 深度缩放 + 贝塞尔曲线连接 + 流动粒子 + 星空 + 拖拽旋转 + 悬停数量 + 点击跳转 | home.js |
| 卡片微交互 | 3D 倾斜 + 跟随鼠标的聚光高光 + 彩色顶边 | home.css / home.js |
| 入场与光标 | IntersectionObserver 逐段揭示、桌面光标光晕、页面隐藏暂停 RAF | home.js |
| 预加载 | 品牌标记 + 进度线，最多 0.9s，避免白屏 | home.css / home.js |

## 2. 性能与降级

- 移动端（≤767px）与 `prefers-reduced-motion`：极光降透明度、轨道/光标/跑马灯动效减弱，知识图改为静态绘制（只画一帧），页面隐藏时暂停动画。
- 所有资源本地加载，无 CDN / 无第三方库，符合 CSP `script-src 'self'`。
- 页面高度变化、窗口 resize、可见性变化都会重新计算画布与星空。

## 3. 迭代方式（ReAct）

1. **Reason**：先确定参考风格的构成（极光、网格、玻璃、流动图、微交互），列出要改的文件与风险（CSP、性能、移动端）。
2. **Act**：实现 aurora.js / index.html / home.css / home.js 四个文件。
3. **Observe**：用无头 Chrome 截图（桌面 1366×900、移动 500×1000、打印 PDF 看整页），发现页头文字在深色下不可见、模块区渐变导致标题发暗、移动端底部导航压住内容、marquee 起始位置等问题。
4. **Refine**：逐项修正（页头配色、模块区纯浅底、移动端 padding、缓存参数），再截图对比，直到通过。

## 4. 可调点

- 主色调：home.css 顶部变量与 `.hero-aura` 的 4 组 rgba；
- 动效强度：`aurora.js` 中 `u_time * 0.045` 流速、`band` 强度；home.js 中节点旋转速度 `spinVel`；
- 知识图节点：home.js 顶部 `CATEGORIES`（颜色/名称/跳转）；
- 若觉得太“重”，把 `#aurora-canvas` 的 opacity 调到 0.5、`.hero-aura` 的 blur 加到 24px。
