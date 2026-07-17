# VALORANT 视频与音频决策辅助系统：完整 Workflow

> 版本：v1.0  
> 定位：个人自用的录像复盘与自定义训练系统  
> 核心约束：游戏运行时不启动 Web；只运行轻量 Rust 后台 Agent。Web 仅用于赛前配置和赛后复盘。

---

## 1. 项目目标

系统通过玩家正常可见、可听到的信息构建战术状态：

- 主视角视频
- 小地图
- HUD
- 击杀栏
- 游戏音频
- 最近若干秒的历史事件

系统持续维护：

- 自己和队友的移动轨迹
- 每名敌人的最后观测
- 敌方区域概率分布
- 当前交战风险
- 可选战术动作及其评分

用户按下快捷键后，服务器基于当前状态返回一条简短建议，例如：

```text
不建议主动拉。右前方风险较高，等队友到位。
```

系统不追求“始终知道敌人的真实坐标”，而是追求：

```text
对可见、可听事件尽量完整捕获
+
对不可见敌人始终维护概率状态
+
明确表达不确定性
```

---

## 2. 使用模式

### 2.1 游戏时模式

游戏时只运行：

```text
valorant-agent.exe
```

不启动：

- 浏览器
- React 页面
- WebView
- Tauri 窗口
- 大型本地 AI 模型

Rust Agent 负责：

- 检测游戏进程和窗口
- 采集视频与音频
- 维护高帧率环形缓存
- 监听全局快捷键
- 上传观测数据
- 接收服务器结果
- 校验结果是否过期
- 使用本地 TTS 播放建议
- 保存日志和决策记录

### 2.2 赛前配置模式

Web Dashboard 用于：

- 设置快捷键
- 设置缓存长度
- 设置画面采样策略
- 设置服务器地址
- 设置输出方式
- 设置建议详细程度
- 测试音频与服务器连接

配置完成后，Rust Agent 读取本地配置文件。Web 可以关闭。

### 2.3 赛后复盘模式

Web Dashboard 用于：

- 播放录像
- 查看自己和队友的路径
- 查看敌方最后发现位置
- 查看敌方区域概率变化
- 查看脚步事件和方向
- 查看按键请求及返回建议
- 查看建议是否过期
- 标注识别错误
- 标注更合理的战术决策
- 导出训练样本

---

## 3. 总体架构

```text
┌──────────────────────────────────────────┐
│ Web Dashboard                            │
│ React + TypeScript                       │
│                                          │
│ 赛前配置 / 赛后复盘 / 人工标注 / 统计       │
└────────────────────┬─────────────────────┘
                     │ HTTPS
                     │ 游戏时可以完全关闭
                     ▼
┌──────────────────────────────────────────┐
│ Python Backend / AI Server               │
│ FastAPI + 推理 Worker                    │
│                                          │
│ 视频解析 / 音频解析 / 状态融合             │
│ 敌方概率 / 对枪风险 / 战术决策             │
│ 数据保存 / 复盘 API                       │
└────────────────────▲─────────────────────┘
                     │ HTTPS / WebSocket
                     │
┌────────────────────┴─────────────────────┐
│ Rust Background Agent                    │
│ 无 WebView、无常驻网页                    │
│                                          │
│ 视频音频采集 / 环形缓存 / 快捷键           │
│ 上传 / 结果校验 / TTS / 本地日志           │
└──────────────────────────────────────────┘
```

---

## 4. 完整端到端 Workflow

## 4.1 赛前配置

```text
打开 Web Dashboard
    ↓
设置采集、快捷键、服务器和语音参数
    ↓
保存配置到服务器
    ↓
下载或同步为本地 agent-config.json
    ↓
关闭 Web
    ↓
启动 Rust Agent
```

建议配置：

```json
{
  "server_url": "https://example.internal",
  "api_token": "personal-token",
  "hotkey": "F8",
  "buffer_seconds": 8,
  "capture_profile": "balanced",
  "output_mode": "voice",
  "voice_language": "zh-CN",
  "max_result_age_ms": 1200,
  "save_match_video": true,
  "save_raw_audio": true
}
```

单人自用时不需要复杂账户体系。一个个人 API Token 即可。

---

## 4.2 Agent 启动

```text
Rust Agent 启动
    ↓
读取本地配置
    ↓
检查采集设备、音频设备、磁盘空间
    ↓
测试服务器连接
    ↓
注册全局快捷键
    ↓
进入 Idle
```

启动检查结果：

```json
{
  "capture_available": true,
  "audio_available": true,
  "server_reachable": true,
  "free_disk_gb": 126.4,
  "hotkey_registered": true
}
```

任何关键检查失败时，不进入采集状态，并写入明确错误日志。

---

## 4.3 游戏检测

Agent 定期检测：

- VALORANT 进程是否存在
- 游戏窗口是否存在
- 窗口是否处于前台
- 当前分辨率是否符合配置
- 音频设备是否仍可用

状态流转：

```text
Idle
  ↓ 检测到游戏
GameDetected
  ↓ 初始化采集
Capturing
```

游戏退出后：

```text
Capturing
  ↓ 游戏退出
Finalizing
  ↓ 保存索引与日志
Idle
```

---

## 4.4 持续视频采集

核心原则：

> 高帧率保存和低帧率常规推理分离。

建议采集策略：

| 数据区域     |     本地缓存帧率 | 常规上传/分析帧率 | 事件精细分析 |
| ------------ | ---------------: | ----------------: | -----------: |
| 完整主视角   |   120 或 144 FPS |         20–30 FPS |   60–144 FPS |
| 准星中心 ROI | 来源于高帧率缓存 |            60 FPS |  120–144 FPS |
| 左右边缘 ROI | 来源于高帧率缓存 |         30–60 FPS |   60–120 FPS |
| 小地图       |           60 FPS |         30–60 FPS |       60 FPS |
| 击杀栏       |        30–60 FPS |            30 FPS |       60 FPS |
| HUD          |           30 FPS |         10–30 FPS |       30 FPS |

完整画面建议只编码一次，ROI 尽量从捕获纹理或解码帧中派生，避免重复捕获。

推荐分区：

```text
1920×1080 原始帧
├─ 中心 ROI：720×720
├─ 左边缘 ROI：320×1080
├─ 右边缘 ROI：320×1080
├─ 小地图 ROI
├─ 击杀栏 ROI
└─ HUD ROI
```

不要将 144 FPS 原始帧持续传给 Web，也不要用 Base64 在进程间搬运高帧率图像。

---

## 4.5 环形视频缓存

Rust Agent 始终只保留最近若干秒：

```text
当前时刻 T
缓存区间：[T - 8 秒, T]
```

环形缓存中记录：

```rust
struct VideoPacketMeta {
    stream_id: u8,
    frame_id: u64,
    capture_timestamp_ns: u64,
    pts: i64,
    keyframe: bool,
    width: u16,
    height: u16,
}
```

需要同时记录：

- 真实捕获时间戳
- 编码时间戳
- 是否重复帧
- 数据流类型
- 分辨率
- 关键帧位置

“文件标注为 144 FPS”不等于获得了 144 张不同画面。应统计有效独立帧率：

```text
effective_fps
=
每秒非重复画面数量
```

---

## 4.6 持续音频采集

音频建议：

```text
48 kHz
双声道 Stereo
保留左右声道
使用 WASAPI Loopback
```

尽量只采集游戏音频，排除：

- 麦克风
- 队伍语音
- 浏览器声音
- 系统提示音
- 本系统自己的 TTS

会话元数据必须记录：

```json
{
  "sample_rate": 48000,
  "channels": 2,
  "hrtf_enabled": true,
  "spatial_audio_mode": "game",
  "effects_volume": 1.0
}
```

音频也使用环形缓存：

```text
最近 8–15 秒 PCM 或低延迟编码音频
```

视频帧与音频包必须使用同一个单调时钟。

---

## 4.7 常规观测上传

有两种运行方式。

### 方式 A：状态流模式

Agent 持续低频上传：

- 小地图
- HUD
- 击杀栏
- 主视角抽帧
- 音频短窗口

服务器持续维护战术状态。

优点：

- 按键后返回更快
- 状态历史完整

缺点：

- 持续占用上传带宽
- 服务端持续消耗资源

### 方式 B：按键批量模式

平时不上传，按键后上传最近若干秒缓存。

优点：

- 本地网络与服务器成本低
- 实现简单

缺点：

- 按键后需要上传和重新解析历史
- 延迟较高

### 推荐方案：混合模式

```text
平时：
小地图 + HUD + 击杀栏低频上传
主视角只上传低频抽帧
音频上传低码率特征或短窗口

按键时：
补传最近 0.8–1.5 秒高帧率主视角
补传最近 5–8 秒小地图和音频
```

---

## 4.8 事件触发

精细分析由以下事件触发：

- 用户按下快捷键
- 主视角发生快速运动变化
- 屏幕边缘出现疑似人物
- 准星附近出现疑似敌人
- 小地图出现敌方标记
- 检测到脚步、枪声或技能声
- 击杀栏发生变化
- 玩家受到伤害

轻量触发器只负责标记时间，不负责做最终判断。

示例：

```json
{
  "trigger_id": "trg_000182",
  "timestamp_ns": 48123000000,
  "type": "manual_hotkey",
  "pre_roll_ms": 1000,
  "post_roll_ms": 300
}
```

---

## 4.9 快捷键请求

用户按下快捷键后：

```text
记录 trigger_timestamp
    ↓
冻结所需缓存索引
    ↓
创建 analysis_request_id
    ↓
上传缺失的高帧率片段
    ↓
发送决策请求
```

请求必须包含：

```json
{
  "request_id": "req_01928",
  "session_id": "session_20260713_001",
  "trigger_timestamp_ns": 48123000000,
  "latest_observation_timestamp_ns": 48118000000,
  "state_version": 1842,
  "max_result_age_ms": 1200,
  "mode": "custom_training",
  "requested_outputs": [
    "enemy_belief",
    "duel_risk",
    "recommendation"
  ]
}
```

---

## 4.10 服务端视频解析

服务端将视频解析拆为多个独立 Skill。

```text
FrameDecodeSkill
    ↓
MainViewDetectionSkill
MinimapParsingSkill
HudParsingSkill
KillFeedParsingSkill
MotionEventSkill
```

### MainViewDetectionSkill

输出：

- 是否有人物进入视野
- 人物边界框
- 出现和消失时间
- 屏幕进入方向
- 是否接近准星
- 是否被遮挡
- 身份是否可确认

短暂出现应融合成事件：

```json
{
  "event_type": "enemy_peek",
  "start_ms": 41206,
  "end_ms": 41231,
  "duration_ms": 25,
  "screen_entry": "right_edge",
  "peak_confidence": 0.83,
  "agent": "unknown"
}
```

第一目标是确认“有人出现”，不是强行识别具体角色。

### MinimapParsingSkill

识别并分类：

```text
self
ally
currently_visible_enemy
recently_seen_enemy
ability_revealed_enemy
unknown_marker
```

小地图标记不应全部解释成实时位置。

### HudParsingSkill

识别：

- 血量
- 护甲
- 武器
- 弹药
- 技能状态
- 回合时间
- 比分
- 存活人数

### KillFeedParsingSkill

识别：

- 击杀者
- 被击杀者
- 武器或技能
- 时间
- 存活状态变化

---

## 4.11 服务端脚步分析

脚步分析分为四层：

```text
声音事件检测
    ↓
相对方向与粗距离估计
    ↓
排除自己和队友
    ↓
映射为地图区域概率
```

### 第一步：音频事件分类

窗口建议：

```text
窗口长度：0.5–1.0 秒
步进：20–50 ms
```

类别：

```text
footstep
jump_or_landing
reload
weapon_equip
gunshot
ability
fake_or_decoy
ambient
voice
unknown
```

输出：

```json
{
  "timestamp_ms": 48230,
  "event": "footstep",
  "probability": 0.91,
  "duration_ms": 180,
  "overlapping_gunfire": false
}
```

### 第二步：方向和距离

先输出离散方向，不强求精确角度：

```text
前
右前
右
右后
后
左后
左
左前
```

距离只输出：

```text
near
medium
far
unknown
```

### 第三步：敌我排除

结合：

- 自己是否正在移动
- 队友位置
- 队友移动轨迹
- 音源方向
- 画面运动
- 小地图状态

先解释哪些声音可能来自自己或队友，剩余部分才作为敌方证据。

### 第四步：地图映射

```text
世界方向
=
玩家当前视角方向
+
声音相对方向
```

再结合：

- 玩家位置
- 地图连通图
- 楼层和高度
- 路径距离
- 墙体与通道
- 敌人历史概率
- 队友已排除区域

输出：

```json
{
  "audio_belief": {
    "A_Main": 0.51,
    "A_Lobby": 0.27,
    "A_Site": 0.14,
    "unknown": 0.08
  }
}
```

脚步事件一般不能单独确认具体敌人身份。

---

## 4.12 事件融合

所有解析结果先变成统一事件：

```json
{
  "event_id": "evt_000923",
  "session_id": "session_20260713_001",
  "timestamp_ns": 48110000000,
  "event_type": "enemy_observed",
  "source": "minimap",
  "entity_id": "enemy_unknown_1",
  "zone_id": "A_Main",
  "confidence": 0.87,
  "payload": {
    "marker_type": "recently_seen"
  }
}
```

事件融合模块负责：

- 时间对齐
- 去重
- 同一事件跨模态合并
- 冲突检测
- 置信度更新
- 事实和推断分离

数据分为两层：

```text
Observation：
画面或音频明确提供的观测

Inference：
根据历史和模型得到的推断
```

绝不能把推断写成已知事实。

---

## 4.13 Tactical State

服务器为当前会话维护：

```python
class TacticalState:
    session_id: str
    state_version: int
    timestamp_ns: int

    map_id: str
    round_id: int
    round_time_ms: int
    side: str

    player_position: tuple[float, float] | None
    player_view_angle: float | None
    player_health: int | None
    player_armor: int | None
    weapon: str | None
    ammo: int | None

    allies: list
    enemies: list

    spike_state: str
    recent_events: list
    uncertainty: dict
```

每次状态更新：

```text
state_version += 1
```

每个决策结果必须引用具体的 `state_version`。

---

## 4.14 地图图模型

地图不只是一张图片，还要转换成图结构：

```text
Zone
├─ zone_id
├─ polygon
├─ center
├─ floor
├─ common_angles
├─ visibility_regions
└─ neighbors
```

边：

```text
Edge
├─ source
├─ target
├─ min_travel_seconds
├─ max_travel_seconds
├─ direction
├─ sound_connectivity
└─ temporary_block_conditions
```

用途：

- 坐标映射到区域
- 计算可能路径
- 排除不可能到达区域
- 估计转点时间
- 将声音方向映射到候选区域
- 建立敌方位置传播模型

---

## 4.15 敌方位置概率

每名存活敌人始终维护一个概率分布：

```json
{
  "enemy_id": "enemy_jett",
  "last_observed": {
    "zone": "A_Main",
    "timestamp_ms": 41230,
    "source": "main_view"
  },
  "zone_probabilities": {
    "A_Main": 0.22,
    "A_Lobby": 0.31,
    "A_Site": 0.18,
    "Mid": 0.21,
    "Other": 0.08
  },
  "uncertainty": "medium"
}
```

推荐第一版使用：

```text
地图图模型
+
粒子滤波
```

粒子随时间沿可行路径传播。

新观测到来时：

```text
主视角发现敌人
→ 粒子集中到可见区域

小地图最近发现标记
→ 提高对应区域概率

队友确认某区域无人
→ 降低该区域权重

脚步来自某方向
→ 提高声音候选区域权重

时间不足以完成转点
→ 删除不可能区域

敌人死亡
→ 移除其位置状态
```

系统可以做到概率空间全覆盖，但不能保证真实位置全覆盖。

---

## 4.16 对枪风险模型

对枪模型输入分为：

### 自身状态

- 血量和护甲
- 武器和弹药
- 移动状态
- 准星位置
- 可用技能
- 玩家个人历史表现

### 敌方估计

- 可能位置
- 可能武器
- 估计血量
- 是否已经暴露
- 是否可能正在换弹
- 站位不确定性

### 几何状态

- 距离
- 掩体比例
- 高低差
- 先看到对手的概率
- 需要转动的角度
- 是否干拉
- 是否处于交叉火力

### 团队状态

- 是否有人补枪
- 双方存活人数
- 是否有技能支持
- 是否会被多人同时接触

第一版建议：

```text
Logistic Regression 基线
+
LightGBM / CatBoost 主模型
+
概率校准
```

输出区间而非虚假精确值：

```json
{
  "estimate": 0.43,
  "lower_bound": 0.34,
  "upper_bound": 0.52,
  "confidence": "medium"
}
```

---

## 4.17 战术决策模型

先选择战术类别：

```text
hold
reposition
regroup
use_utility
gather_information
rotate
retake
save
take_duel
```

再在类别中选择具体动作。

评分可表示为：

```text
Action Score
=
预计回合胜率变化
+ 信息价值
+ 地图控制价值
+ 队友协同价值
- 死亡代价
- 经济损失
- 技能消耗
- 不确定性惩罚
```

输出候选动作：

```json
[
  {
    "action": "hold_angle",
    "score": 0.67
  },
  {
    "action": "regroup",
    "score": 0.61
  },
  {
    "action": "dry_peek",
    "score": 0.24
  }
]
```

最终只给用户一条建议，避免信息过载。

---

## 4.18 解释生成

实时热路径不依赖云端大语言模型。

优先使用模板：

```text
{action_text}。{primary_risk}，{support_reason}。
```

例如：

```text
不建议主动拉。右前方风险较高，目前没有队友可以补枪。
```

模板输入来自结构化结果，不能自行编造胜率、位置或原因。

大语言模型只用于：

- 赛后详细解释
- 整局总结
- 错误模式归纳
- 训练计划
- 标注辅助

---

## 4.19 结果返回

服务器返回：

```json
{
  "request_id": "req_01928",
  "session_id": "session_20260713_001",
  "state_version": 1842,
  "state_timestamp_ns": 48118000000,
  "generated_at_ns": 48310000000,
  "recommendation": {
    "category": "avoid_duel",
    "action": "hold_and_wait",
    "confidence": 0.74
  },
  "enemy_belief": [
    {
      "zone": "A_Main",
      "probability": 0.46,
      "evidence": [
        "minimap_recently_seen",
        "footstep_right_front"
      ]
    },
    {
      "zone": "Mid",
      "probability": 0.29,
      "evidence": [
        "movement_model"
      ]
    }
  ],
  "duel": {
    "estimate": 0.41,
    "lower_bound": 0.33,
    "upper_bound": 0.51,
    "confidence": "medium"
  },
  "spoken_text": "不建议主动拉，先等队友靠近。",
  "model_versions": {
    "vision": "vision-0.1",
    "audio": "audio-0.1",
    "belief": "belief-0.1",
    "policy": "policy-0.1"
  }
}
```

---

## 4.20 Agent 时效校验

Agent 收到结果后，必须校验：

```text
当前时间 - state_timestamp
```

如果超过：

```text
max_result_age_ms
```

则丢弃，不播放。

还应校验：

- `session_id` 是否匹配
- `request_id` 是否仍为当前请求
- `state_version` 是否过旧
- 游戏窗口是否仍处于有效状态
- 玩家是否已死亡或回合是否结束

示例：

```rust
fn should_play(result: &DecisionResult, now_ns: u64) -> bool {
    if result.session_id != current_session_id() {
        return false;
    }

    let age_ms = (now_ns - result.state_timestamp_ns) / 1_000_000;

    age_ms <= configured_max_result_age_ms()
}
```

---

## 4.21 本地输出

推荐优先级：

```text
1. 本地 TTS
2. 极简系统通知
3. 第二设备或第二屏
4. 普通独立小窗口
```

游戏时不需要打开 Web。

语音应满足：

- 一次只说一个结论
- 句子尽量短
- 明确不确定性
- 不播放已过期结果
- 新请求可取消旧语音
- TTS 音频不能重新进入脚步采集通道

---

## 4.22 赛后保存

游戏结束后：

```text
停止采集
    ↓
写入最终视频索引
    ↓
保存事件和状态快照
    ↓
保存决策请求与结果
    ↓
生成 session summary
    ↓
上传或同步复盘数据
```

建议目录：

```text
data/
└─ session_20260713_001/
   ├─ metadata.json
   ├─ video/
   │  ├─ main.mkv
   │  └─ index.json
   ├─ audio/
   │  └─ game_audio.flac
   ├─ events.parquet
   ├─ observations.parquet
   ├─ states.parquet
   ├─ decisions.parquet
   ├─ annotations.parquet
   ├─ keyframes/
   └─ logs/
      ├─ agent.jsonl
      └─ server.jsonl
```

---

## 4.23 Web 复盘

```text
用户稍后打开 Web
    ↓
选择一场 Session
    ↓
加载录像、事件、轨迹和状态
    ↓
时间轴同步播放
    ↓
查看每个决策点
    ↓
纠正观测或战术建议
    ↓
保存标注
```

Web 页面建议：

```text
Dashboard
Sessions
Replay
Timeline
Map
Decision Review
Annotations
Models
Settings
```

复盘页面布局：

```text
┌───────────────────┬────────────────────┐
│ 录像播放器         │ 地图与概率热力图     │
├───────────────────┴────────────────────┤
│ 时间轴：脚步 / 发现 / 击杀 / 决策请求     │
├────────────────────────────────────────┤
│ 当前 Tactical State 与模型依据           │
├────────────────────────────────────────┤
│ 人工标注与修正                           │
└────────────────────────────────────────┘
```

---

## 4.24 反馈与训练闭环

人工纠正记录：

```json
{
  "decision_id": "decision_193",
  "model_action": "hold",
  "reviewer_action": "regroup",
  "model_confidence": 0.74,
  "reviewer_confidence": 0.90,
  "reason_codes": [
    "no_trade_support",
    "enemy_numbers_advantage"
  ]
}
```

训练数据分为：

```text
事实标签：
位置、血量、时间、击杀、脚步事件

结果标签：
对枪胜负、是否被补枪、回合结果

教练标签：
推荐动作、风险等级、关键原因
```

一次低概率决策成功，不代表该决策本身正确。不能只以回合输赢作为标签。

---

## 5. Rust Agent 设计

## 5.1 状态机

```rust
enum AgentState {
    Idle,
    GameDetected,
    InitializingCapture,
    Capturing,
    PreparingRequest,
    Uploading,
    WaitingForResult,
    Speaking,
    Finalizing,
    Recovering,
    Error,
}
```

主要流转：

```text
Idle
→ GameDetected
→ InitializingCapture
→ Capturing
→ PreparingRequest
→ Uploading
→ WaitingForResult
→ Speaking
→ Capturing
```

异常流转：

```text
任意运行状态
→ Recovering
→ Capturing 或 Idle
```

---

## 5.2 Rust Agent 模块

```text
valorant-agent/
├─ process_detector
├─ window_detector
├─ capture
│  ├─ windows_graphics_capture
│  ├─ frame_clock
│  ├─ roi
│  └─ duplicate_detector
├─ audio
│  ├─ wasapi_loopback
│  └─ audio_clock
├─ buffer
│  ├─ video_ring
│  ├─ audio_ring
│  └─ snapshot
├─ encoder
│  ├─ nvenc
│  ├─ quick_sync
│  ├─ amf
│  └─ software_fallback
├─ hotkey
├─ uploader
├─ websocket
├─ result_validator
├─ tts
├─ config
├─ storage
├─ telemetry
└─ tray
```

---

## 5.3 线程与任务划分

```text
Main Control Task
├─ 状态机
├─ 配置
└─ 生命周期

Video Capture Thread
├─ 捕获纹理
├─ 时间戳
└─ 放入编码队列

Audio Capture Thread
├─ WASAPI Loopback
├─ 时间戳
└─ 放入音频环形缓存

Encoder Thread
├─ 硬件编码
└─ 写入视频环形缓存

Network Runtime
├─ 上传
├─ WebSocket
└─ 重试

Output Task
├─ 结果校验
└─ TTS

Log Writer
└─ 异步结构化日志
```

线程之间使用有界队列。队列满时，应按策略丢弃非关键预览帧，不能阻塞游戏采集线程。

---

## 5.4 少复制原则

高性能关键不是语言本身，而是减少数据复制。

避免：

```text
GPU
→ CPU 完整帧
→ 新建图像对象
→ 裁剪复制
→ JPEG
→ Base64
→ JSON
```

推荐：

```text
GPU 捕获纹理
→ GPU 裁剪/缩放或编码器输入
→ 硬件编码
→ 环形缓冲
```

小元数据单独传输：

```json
{
  "frame_id": 92831,
  "timestamp_ns": 48123000000,
  "stream": "main",
  "width": 1280,
  "height": 720
}
```

---

## 5.5 资源控制

Agent 必须设置上限：

```text
最大内存缓存
最大磁盘占用
最大上传带宽
最大并发请求数
最大重试次数
最长 TTS 队列
```

建议：

```json
{
  "max_memory_mb": 768,
  "max_disk_gb": 30,
  "max_upload_mbps": 20,
  "max_inflight_requests": 1,
  "request_timeout_ms": 1500,
  "max_retries": 1
}
```

按键连续触发时：

- 默认取消旧请求，只保留最新请求
- 或在 300–500 ms 内防抖
- 不允许积累多个已过期结果

---

## 6. Python Server 设计

## 6.1 服务划分

```text
API Service
├─ 会话管理
├─ 配置
├─ 上传
└─ 决策请求

Media Worker
├─ 解码
├─ 帧抽取
└─ 音频窗口

Vision Worker
├─ 主视角
├─ 小地图
├─ HUD
└─ 击杀栏

Audio Worker
├─ 脚步检测
├─ 方向估计
└─ 事件分类

State Service
├─ 事件融合
├─ Tactical State
└─ Enemy Belief

Decision Worker
├─ 对枪模型
├─ 行动评分
└─ 解释模板

Review Service
├─ 录像索引
├─ 时间轴
├─ 标注
└─ 数据导出
```

第一版可以部署在同一个 Python 项目中，但代码边界应按上述职责划分。

---

## 6.2 Skill 接口

```python
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass
class SkillContext:
    session_id: str
    state_version: int
    timestamp_ns: int
    task: str
    payload: dict[str, Any]
    deadline_ms: int


@dataclass
class SkillResult:
    success: bool
    skill_name: str
    data: dict[str, Any]
    confidence: float
    elapsed_ms: int
    model_version: str
    error: str | None = None


class Skill(Protocol):
    name: str

    def can_handle(self, context: SkillContext) -> bool:
        ...

    def run(self, context: SkillContext) -> SkillResult:
        ...
```

Skill 列表：

```text
FrameDecodeSkill
MainViewDetectionSkill
MinimapParsingSkill
HudParsingSkill
KillFeedParsingSkill
AudioEventSkill
AudioDirectionSkill
EventFusionSkill
EnemyBeliefSkill
DuelRiskSkill
TacticalPolicySkill
ExplanationSkill
ReviewSummarySkill
```

---

## 6.3 热路径调度

```text
决策请求到达
    ↓
检查当前 state_version 和状态新鲜度
    ↓
缺少必要数据？
    ├─ 是：优先解析补传的关键片段
    └─ 否：直接使用当前状态
    ↓
并行运行必要的视觉与音频 Skill
    ↓
事件融合
    ↓
更新 Enemy Belief
    ↓
运行 DuelRisk
    ↓
运行 TacticalPolicy
    ↓
模板生成一句话
    ↓
返回
```

不相关的赛后分析任务不能占用实时队列。

---

## 6.4 实时与离线队列分离

```text
realtime-high
├─ 按键决策
└─ 状态补充解析

background-normal
├─ 常规抽帧
├─ 完整录像索引
└─ 赛后复盘

training-low
├─ 样本生成
├─ 批量评估
└─ 模型训练
```

实时队列始终拥有最高优先级。

---

## 7. API 设计

## 7.1 Agent 配置

```text
GET /v1/agent/config
PUT /v1/agent/config
```

## 7.2 创建会话

```text
POST /v1/sessions
```

请求：

```json
{
  "mode": "custom_training",
  "resolution": {
    "width": 1920,
    "height": 1080
  },
  "capture_profile": "balanced",
  "audio_profile": "stereo_hrtf"
}
```

## 7.3 上传观测

```text
POST /v1/sessions/{session_id}/observations
```

支持：

- 分片上传
- 内容哈希
- 幂等键
- 断点续传
- 时间戳范围

## 7.4 决策请求

```text
POST /v1/sessions/{session_id}/decisions
```

## 7.5 实时事件通道

```text
WS /v1/sessions/{session_id}/stream
```

传输：

- 上传确认
- 当前状态版本
- 决策结果
- 服务端错误
- 模型降级信息

## 7.6 结束会话

```text
POST /v1/sessions/{session_id}/finalize
```

## 7.7 复盘

```text
GET /v1/sessions
GET /v1/sessions/{session_id}
GET /v1/sessions/{session_id}/timeline
GET /v1/sessions/{session_id}/states
GET /v1/sessions/{session_id}/decisions
POST /v1/sessions/{session_id}/annotations
```

---

## 8. 数据库与存储

单人自用建议：

```text
元数据：
SQLite 起步
后续需要远程多设备时再切 PostgreSQL

事件与训练表：
Parquet

视频与音频：
本地磁盘或 S3/MinIO

缓存：
内存
必要时使用 Redis
```

核心表：

```text
sessions
media_segments
events
observations
state_snapshots
enemy_beliefs
decision_requests
decision_results
annotations
model_versions
agent_logs
```

所有记录包含：

```text
session_id
timestamp_ns
created_at
schema_version
model_version
```

---

## 9. 鲁棒性设计

## 9.1 超时与降级

```text
深度视觉分析超时
→ 使用已有 Tactical State

音频方向模型失败
→ 仅保留“检测到疑似脚步”

敌人身份无法确认
→ 使用 unknown_enemy

对枪模型缺少输入
→ 返回风险等级，不返回精确概率

服务器不可用
→ Agent 继续本地缓存并提示不可用
```

---

## 9.2 重连

WebSocket 断开后：

```text
指数退避
+
最大等待上限
+
恢复后发送当前 session_id 和最后确认序号
```

上传使用幂等键：

```text
session_id + stream_id + segment_start_ns + content_hash
```

避免重试产生重复数据。

---

## 9.3 数据完整性

每个片段包含：

```text
SHA-256
起止时间戳
帧数量
音频样本数量
编码参数
schema_version
```

服务端校验失败时明确请求重传。

---

## 9.4 崩溃恢复

Agent 定期写入轻量 Checkpoint：

```json
{
  "session_id": "session_20260713_001",
  "state": "Capturing",
  "last_video_segment": 182,
  "last_audio_segment": 183,
  "last_uploaded_segment": 178
}
```

Agent 重启后可以：

- 关闭损坏的媒体片段
- 恢复未完成上传
- 标记异常结束的 Session
- 保留已采集数据

---

## 9.5 时钟与同步

统一使用单调时钟记录实时事件，使用 UTC 记录跨设备时间。

```text
monotonic_timestamp_ns：
用于视频、音频、事件同步

utc_timestamp：
用于日志、文件和服务器记录
```

定期估计 Agent 与服务器的时钟偏差，但决策新鲜度优先使用 Agent 本地单调时钟。

---

## 10. 性能预算

目标不是保证固定延迟，而是给每一环设置预算和截止时间。

参考预算：

| 环节               |   目标范围 |
| ------------------ | ---------: |
| 快捷键处理与快照   |    1–10 ms |
| 缓存索引与片段固化 |    5–30 ms |
| 上传补充片段       | 20–250+ ms |
| 服务端解码         |   10–80 ms |
| 视觉解析           |  30–200 ms |
| 音频解析           |  10–100 ms |
| 状态融合           |    1–20 ms |
| 敌方概率更新       |    2–30 ms |
| 对枪与决策         |    1–30 ms |
| 返回网络           | 20–100+ ms |
| TTS 开始播放       |  30–150 ms |

关键指标：

```text
end_to_end_latency_ms
result_age_ms
expired_result_rate
capture_effective_fps
dropped_frame_rate
upload_queue_depth
server_queue_wait_ms
```

---

## 11. 评估指标

## 11.1 视频识别

```text
人物检测 Precision / Recall
快速 peek 事件召回率
小地图图标分类准确率
HUD 字段准确率
击杀事件准确率
有效帧率
```

快速 peek 单独按持续时间分桶：

```text
0–16 ms
16–33 ms
33–66 ms
66–100 ms
100 ms 以上
```

---

## 11.2 音频

```text
脚步检测 Precision / Recall
敌我排除准确率
八方向分类准确率
距离等级准确率
技能或假声音误报率
```

---

## 11.3 轨迹与位置概率

```text
己方坐标误差
轨迹中断次数
敌人 Top-1 区域命中率
敌人 Top-3 区域命中率
Brier Score
概率校准误差
高置信度错误率
```

---

## 11.4 决策

```text
与人工复盘意见一致率
建议过时率
高置信度错误率
无法给出建议的比例
原因解释正确率
```

回合胜负只能作为辅助指标。

---

## 12. 推荐仓库结构

```text
valorant-decision-system/
├─ agent-rust/
│  ├─ Cargo.toml
│  ├─ src/
│  │  ├─ main.rs
│  │  ├─ state_machine.rs
│  │  ├─ capture/
│  │  ├─ audio/
│  │  ├─ buffer/
│  │  ├─ encoder/
│  │  ├─ network/
│  │  ├─ output/
│  │  ├─ config/
│  │  └─ telemetry/
│  └─ tests/
│
├─ server-python/
│  ├─ pyproject.toml
│  ├─ app/
│  │  ├─ api/
│  │  ├─ skills/
│  │  ├─ media/
│  │  ├─ vision/
│  │  ├─ audio/
│  │  ├─ state/
│  │  ├─ belief/
│  │  ├─ decision/
│  │  ├─ storage/
│  │  └─ workers/
│  ├─ models/
│  └─ tests/
│
├─ web-dashboard/
│  ├─ package.json
│  ├─ src/
│  │  ├─ pages/
│  │  ├─ components/
│  │  ├─ replay/
│  │  ├─ timeline/
│  │  ├─ map/
│  │  ├─ annotations/
│  │  └─ api/
│  └─ tests/
│
├─ shared-schema/
│  ├─ json-schema/
│  └─ generated/
│
├─ map-data/
│  ├─ maps/
│  ├─ zones/
│  └─ navigation-graphs/
│
├─ datasets/
├─ deployment/
├─ docs/
└─ scripts/
```

共享数据结构建议用 JSON Schema 定义，再生成 Rust、Python 和 TypeScript 类型，避免三端字段漂移。

---

## 13. 分阶段开发计划

## Phase 0：固定实验条件

先固定：

```text
一台电脑
一种分辨率
一种 HUD 比例
一种音频设置
一张地图
录像或自定义训练素材
```

完成：

- 统一时间戳方案
- 文件和事件 Schema
- 基础测试数据集

---

## Phase 1：Rust 采集 Agent

目标：

```text
检测游戏
→ 采集 120/144 FPS 视频
→ 采集 48 kHz 双声道音频
→ 维护 8 秒环形缓存
→ 快捷键固化片段
→ 保存到本地
```

验收：

- 长时间运行稳定
- 不明显影响游戏帧率
- 音视频同步误差可测
- 崩溃后数据可恢复
- 有效独立帧率达到目标

---

## Phase 2：离线解析

目标：

```text
解析录像
→ 自动识别回合
→ 解析小地图
→ 记录自己和队友路径
→ 记录敌人发现事件
→ 解析击杀栏与 HUD
```

暂时不做实时决策。

---

## Phase 3：快速露头与脚步

目标：

```text
高帧率主视角检测
→ 生成 enemy_peek 事件

音频事件检测
→ 八方向脚步
→ 排除自己和队友
```

验收：

- 短时露头分桶评估
- 脚步事件误报率可接受
- 视频音频事件可在同一时间轴查看

---

## Phase 4：地图图模型与 Enemy Belief

目标：

```text
地图区域图
→ 最后发现位置
→ 粒子传播
→ 多模态观测更新
→ 区域概率热力图
```

验收：

- Top-1 / Top-3 区域准确率
- Brier Score
- 概率校准曲线
- 高置信度错误率

---

## Phase 5：Web 复盘

目标：

```text
录像 + 地图 + 时间轴
→ 查看事件
→ 查看概率变化
→ 人工纠正
→ 保存标注
```

Web 与游戏不同时运行。

---

## Phase 6：服务器实时请求

目标：

```text
Agent 低频上传
→ 快捷键补传高帧率片段
→ 服务器更新状态
→ 返回结构化结果
→ Agent 校验后 TTS
```

先在录像回放或自定义训练环境测试。

---

## Phase 7：对枪风险与战术决策

目标：

```text
提取特征
→ 建立可解释基线
→ 训练校准模型
→ 候选行动评分
→ 输出一条建议
```

第一版应允许返回：

```text
信息不足，暂不建议主动行动。
```

---

## Phase 8：反馈训练闭环

目标：

```text
复盘标注
→ 自动生成训练样本
→ 模型离线评估
→ 新旧模型对比
→ 灰度切换模型版本
```

---

## 14. 最小可用版本 MVP

第一版真正需要完成的只有：

```text
Rust Agent
├─ 游戏检测
├─ 视频/音频采集
├─ 8 秒环形缓存
├─ 快捷键
└─ 上传

Python Server
├─ 小地图解析
├─ 主视角人物事件
├─ 脚步检测
├─ 事件时间线
└─ 简单敌方区域概率

Web
├─ Session 列表
├─ 录像播放器
├─ 地图轨迹
├─ 事件时间轴
└─ 人工纠正
```

第一版暂时不需要：

- 大语言模型实时推理
- 强化学习
- 多智能体系统
- 精确敌人坐标
- 自动输入控制
- 游戏内存读取
- Web 游戏内覆盖层
- 多用户权限
- 复杂云原生集群

---

## 15. 推荐技术栈

### Rust Agent

```text
Rust
Tokio
Windows Graphics Capture
WASAPI Loopback
Windows 全局快捷键
FFmpeg 或硬件编码封装
reqwest / tungstenite
serde
tracing
SQLite 或 JSONL 本地日志
```

### Python Server

```text
Python
FastAPI
Pydantic
OpenCV
PyTorch
ONNX Runtime
TensorRT（后期）
LightGBM / CatBoost
Polars / Pandas
PyArrow / Parquet
SQLite 或 PostgreSQL
```

### Web Dashboard

```text
React
TypeScript
Vite
Zustand
Konva.js 或 PixiJS
ECharts
视频播放器
Canvas / SVG 时间轴
```

---

## 16. 核心工程原则

### 原则一：Web 与游戏解耦

```text
游戏时：
Rust Agent

赛前和赛后：
Web Dashboard
```

### 原则二：高帧率缓存不等于高帧率全量推理

```text
高帧率保存
+
低帧率常规分析
+
事件片段高帧率重放
```

### 原则三：事实与推断分离

```text
Observation ≠ Inference
```

### 原则四：概率全覆盖，不承诺真实位置全覆盖

每名敌人始终有概率分布，但不虚构精确位置。

### 原则五：所有输出都带时间戳和状态版本

过期建议必须丢弃。

### 原则六：实时热路径不用大语言模型

结构化模型负责判断，模板负责短句输出。

### 原则七：先做数据闭环，再追求高级模型

```text
采集
→ 解析
→ 复盘
→ 标注
→ 评估
→ 训练
```

### 原则八：出现性能瓶颈后再优化

先测量：

- 捕获耗时
- 复制次数
- 编码耗时
- 上传耗时
- 推理耗时
- 队列等待

再决定是否引入 C++、CUDA 或 TensorRT。

---

## 17. 最终工作流摘要

```text
赛前
Web 配置
    ↓
配置同步到 Rust Agent
    ↓
关闭 Web

游戏时
Rust Agent 检测游戏
    ↓
高帧率视频 + 双声道音频环形缓存
    ↓
低频上传关键 ROI 与事件
    ↓
用户按快捷键
    ↓
补传最近高帧率片段
    ↓
Python Server 多模态解析
    ↓
事件融合与 Tactical State
    ↓
Enemy Belief 概率更新
    ↓
对枪风险和候选行动评分
    ↓
返回带时间戳和 state_version 的结果
    ↓
Rust Agent 检查结果年龄
    ↓
未过期则本地 TTS 播放

赛后
结束 Session
    ↓
保存录像、音频、事件、状态和决策
    ↓
稍后打开 Web
    ↓
录像复盘、地图热力图、时间轴
    ↓
人工纠正与标注
    ↓
生成训练数据
    ↓
模型评估与迭代
```

---

## 18. 下一步开工顺序

建议立即从下面四项开始：

1. 定义共享 JSON Schema：Session、Event、Observation、Decision。
2. 用 Rust 完成视频、音频和统一时间戳环形缓存。
3. 用 Python 完成录像导入、时间轴和小地图 ROI 解析。
4. 用 React 做最小复盘页：播放器、地图、事件列表。

在这四项稳定之前，不要急着实现完整战术指挥模型。它们构成整个系统的数据基础和调试基础。