# VALORANT Detector Architecture

> 目标：把 `workflow.md` 里的系统想法落成可实现的工程结构。  
> 范围：模块边界、数据结构、Rust/Python 接口、存储格式、API、MVP 到实时版本的实施顺序。

---

## 1. 文档定位

`workflow.md` 负责回答：

```text
系统想做什么
用户如何使用
整体工作流是什么
分阶段应该先做什么
```

本文档负责回答：

```text
代码应该怎么分层
数据应该怎么存
Rust 和 Python 应该怎么通信
服务端 API 应该怎么设计
第一版具体从哪里开工
后续如何平滑升级到实时采集
```

核心原则：

- 游戏时不启动 Web Dashboard。
- 不读取游戏内存，不注入进程，不做自动输入。
- 视频、音频和玩家正常可见/可听信息是唯一输入。
- 原始证据、观察事实、推断状态和决策建议必须分层保存。
- 第一版优先完成离线数据闭环，不急着实现完整实时指挥。

---

## 2. 系统分层

目标架构分为四层：

```text
Web Dashboard
  赛前配置 / 赛后复盘 / 人工标注 / 数据导出

Python Server
  API / 录像导入 / 视觉音频解析 / 状态融合 / 决策 / 存储

Python Workers
  Vision / Audio / Review / Training

Rust Agent
  游戏检测 / 视频音频采集 / 环形缓存 / 快捷键 / 上传 / TTS
```

第一版可以只实现：

```text
FastAPI Server
  ↓
上传截图或录像
  ↓
Python/OpenCV 解析
  ↓
写 Observation JSONL 或 Parquet
  ↓
返回结构化结果
```

等数据结构稳定后，再升级为：

```text
Rust Agent
  ↓ FrameDescriptor
Python VisionWorker
  ↓ ObservationBatch
Python StateService
  ↓ TacticalState / DecisionResult
Rust Agent
  ↓ TTS / 本地日志
```

---

## 3. 推荐仓库结构

当前仓库已有：

```text
valorant_detector/
├─ agent/
├─ dashboard/
├─ docs/
├─ server/
├─ pyproject.toml
└─ uv.lock
```

建议逐步扩展为：

```text
valorant_detector/
├─ agent/
│  ├─ Cargo.toml
│  └─ src/
│     ├─ main.rs
│     ├─ state_machine.rs
│     ├─ capture/
│     ├─ audio/
│     ├─ buffer/
│     ├─ encoder/
│     ├─ network/
│     ├─ hotkey/
│     ├─ output/
│     └─ config/
│
├─ server/
│  ├─ src/
│  │  ├─ main.py
│  │  └─ app/
│  │     ├─ api/
│  │     ├─ core/
│  │     ├─ schemas/
│  │     ├─ media/
│  │     ├─ vision/
│  │     ├─ audio/
│  │     ├─ state/
│  │     ├─ decision/
│  │     ├─ storage/
│  │     └─ workers/
│  └─ tests/
│
├─ dashboard/
│  ├─ package.json
│  └─ src/
│     ├─ pages/
│     ├─ components/
│     ├─ replay/
│     ├─ timeline/
│     ├─ map/
│     └─ api/
│
├─ shared_schema/
│  ├─ proto/
│  ├─ json_schema/
│  └─ generated/
│
├─ data/
│  ├─ sessions/
│  ├─ datasets/
│  └─ exports/
│
├─ map_data/
│  ├─ maps/
│  ├─ zones/
│  └─ navigation_graphs/
│
├─ docs/
└─ scripts/
```

短期不需要一次创建所有目录。建议先创建 `server/src/app`、`shared_schema/json_schema` 和 `data/sessions`。

---

## 4. 运行模式

### 4.1 离线 MVP 模式

用途：先验证截图、录像、HUD、小地图和事件数据结构。

```text
用户上传截图或录像
  ↓
FastAPI 保存原始文件
  ↓
Python 解析基础元数据
  ↓
Vision 模块裁剪 ROI
  ↓
生成 ObservationEvent
  ↓
StateService 聚合状态
  ↓
保存到本地 data/sessions
```

这个阶段不需要 Rust，也不需要共享内存。

### 4.2 赛后复盘模式

用途：验证数据闭环。

```text
录像文件
  ↓
批量抽帧
  ↓
HUD / Minimap / KillFeed / MainView 解析
  ↓
事件时间轴
  ↓
状态快照
  ↓
Web 复盘和人工纠错
```

### 4.3 自定义房间实时模式

用途：验证低延迟链路，不用于正式匹配。

```text
Rust Agent 采集
  ↓
高帧率环形缓存
  ↓
低频 FrameDescriptor 发送给 Python
  ↓
Python 返回 ObservationBatch
  ↓
服务器更新 TacticalState
  ↓
快捷键请求 DecisionResult
  ↓
Rust 校验时效后 TTS 播放
```

---

## 5. 数据分层

每场 Session 至少保存四层数据。

### 5.1 原始证据层

原始输入必须保留，方便未来用新模型重新解析。

```json
{
  "video_id": "video_001",
  "session_id": "session_001",
  "path": "data/sessions/session_001/video/source.mp4",
  "width": 1920,
  "height": 1080,
  "fps": 60.0,
  "duration_ms": 328400,
  "codec": "h264",
  "sha256": "..."
}
```

截图 MVP 也用同样思想：

```json
{
  "image_id": "image_001",
  "session_id": "session_001",
  "path": "data/sessions/session_001/images/frame_001.png",
  "width": 1920,
  "height": 1080,
  "sha256": "..."
}
```

### 5.2 观察事件层

Observation 表示画面或音频明确提供的事实，不表示推断。

```json
{
  "observation_id": "obs_000184",
  "session_id": "session_001",
  "round_id": "round_01",
  "timestamp_ms": 68420,
  "frame_id": 4105,
  "source": "minimap",
  "kind": "position_observed",
  "entity_id": "ally_2",
  "confidence": 0.94,
  "payload": {
    "x": 0.613,
    "y": 0.427,
    "zone_id": "a_main"
  },
  "model_version": "minimap-detector-0.1"
}
```

常见 `kind`：

```text
health_observed
armor_observed
ammo_observed
weapon_observed
position_observed
enemy_seen
enemy_lost
kill_observed
death_observed
footstep_detected
gunshot_detected
round_started
round_ended
spike_planted
spike_defused
```

识别错误时不要删除原事件，而是追加修正事件：

```json
{
  "observation_id": "obs_fix_000184",
  "session_id": "session_001",
  "timestamp_ms": 91000,
  "source": "manual",
  "kind": "observation_corrected",
  "confidence": 1.0,
  "payload": {
    "corrects_observation_id": "obs_000184",
    "field": "payload.zone_id",
    "new_value": "a_lobby"
  }
}
```

### 5.3 轨迹层

己方轨迹可以来自小地图持续观测。敌方轨迹通常只能保存为“最后观测 + 概率传播”。

```json
{
  "track_id": "track_ally_2_round_01",
  "session_id": "session_001",
  "round_id": "round_01",
  "entity_id": "ally_2",
  "start_ms": 62000,
  "end_ms": 79400,
  "segments": [
    {
      "from_zone": "a_lobby",
      "to_zone": "a_main",
      "start_ms": 62000,
      "end_ms": 67100,
      "observed": true,
      "confidence": 0.88
    }
  ]
}
```

细粒度点位可以作为样本保存：

```json
{
  "timestamp_ms": 67100,
  "entity_id": "ally_2",
  "x": 0.612,
  "y": 0.431,
  "zone_id": "a_main",
  "observed": true,
  "uncertainty_radius": 0.012
}
```

`observed=false` 只能表示插值或模型传播，不能当作真实标签。

### 5.4 状态和决策层

`TacticalState` 是多个 Observation 聚合后的当前局面。

```json
{
  "session_id": "session_001",
  "round_id": "round_01",
  "state_version": 1842,
  "timestamp_ms": 68420,
  "player": {
    "health": 73,
    "armor": 25,
    "weapon": "vandal",
    "ammo": 18,
    "zone_id": "a_main"
  },
  "allies": [],
  "enemy_beliefs": [
    {
      "enemy_id": "enemy_unknown_1",
      "zone_probabilities": {
        "a_main": 0.46,
        "mid": 0.29,
        "other": 0.25
      },
      "uncertainty": "medium"
    }
  ],
  "recent_events": []
}
```

决策结果单独保存，并绑定 `state_version`：

```json
{
  "decision_id": "decision_000284",
  "session_id": "session_001",
  "round_id": "round_01",
  "state_version": 1842,
  "timestamp_ms": 68420,
  "recommended_action": "hold_angle",
  "candidate_actions": [
    {
      "action": "hold_angle",
      "score": 0.72
    },
    {
      "action": "regroup",
      "score": 0.63
    },
    {
      "action": "dry_peek",
      "score": 0.31
    }
  ],
  "reasons": [
    "no_trade_teammate",
    "enemy_angle_advantage"
  ],
  "model_version": "policy-0.1"
}
```

---

## 6. 核心 Python 数据模型

第一版建议用 Pydantic 定义 API 和存储模型。

```python
from typing import Any, Literal

from pydantic import BaseModel, Field


class Estimate(BaseModel):
    value: Any | None
    confidence: float = Field(ge=0.0, le=1.0)
    source: str


class ObservationEvent(BaseModel):
    observation_id: str
    session_id: str
    round_id: str | None = None
    frame_id: int | None = None
    timestamp_ms: int
    source: Literal["hud", "minimap", "main_view", "killfeed", "audio", "manual"]
    kind: str
    entity_id: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    payload: dict[str, Any]
    model_version: str | None = None


class PlayerState(BaseModel):
    health: Estimate | None = None
    armor: Estimate | None = None
    weapon: Estimate | None = None
    ammo: Estimate | None = None
    zone_id: Estimate | None = None


class TacticalState(BaseModel):
    session_id: str
    state_version: int
    timestamp_ms: int
    round_id: str | None = None
    player: PlayerState
    allies: list[dict[str, Any]] = []
    enemy_beliefs: list[dict[str, Any]] = []
    recent_events: list[ObservationEvent] = []
    uncertainty: dict[str, Any] = {}
```

规则：

- `ObservationEvent` 只追加。
- `TacticalState` 可以定期快照。
- 不确定字段必须允许 `None`。
- 每个识别值都要有 `confidence` 和 `source`。
- 每个模型输出都要带 `model_version`。

---

## 7. Skill 接口

Python Server 内部使用统一 Skill 接口，避免每个模块直接互相调用。

```python
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class SkillContext:
    session_id: str
    state_version: int | None
    timestamp_ms: int
    task: str
    payload: dict[str, Any]
    deadline_ms: int


@dataclass(frozen=True)
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

建议的 Skill：

```text
FrameDecodeSkill
HudParsingSkill
MinimapParsingSkill
KillFeedParsingSkill
MainViewDetectionSkill
AudioEventSkill
AudioDirectionSkill
EventFusionSkill
EnemyBeliefSkill
DuelRiskSkill
TacticalPolicySkill
ExplanationSkill
ReviewSummarySkill
```

实时热路径中，`ExplanationSkill` 应使用模板，不依赖云端大语言模型。

---

## 8. Rust 与 Python 的接口

不要用 JSON 或 HTTP 传高频视频帧。

推荐分三种接口：

```text
实时大帧数据：
共享内存环形缓冲区

控制与结构化结果：
gRPC 双向流 + Protobuf

离线训练数据：
Apache Arrow / Parquet
```

### 8.1 MVP 阶段

先不做共享内存。Python 直接读取文件：

```text
POST /v1/sessions
POST /v1/sessions/{session_id}/media
POST /v1/sessions/{session_id}/analyze
GET  /v1/sessions/{session_id}/timeline
```

### 8.2 实时阶段

Rust 只传帧引用，Python 返回结构化观察。

```protobuf
syntax = "proto3";

package valorant.v1;

message FrameDescriptor {
  string session_id = 1;
  uint64 frame_id = 2;
  int64 timestamp_ns = 3;

  string shared_memory_name = 4;
  uint32 slot_id = 5;
  uint64 generation = 6;

  uint64 offset = 7;
  uint64 length = 8;

  uint32 width = 9;
  uint32 height = 10;
  uint32 stride = 11;
  string pixel_format = 12;

  string stream = 13;
}

message Observation {
  string observation_id = 1;
  uint64 frame_id = 2;
  int64 timestamp_ns = 3;

  string entity_id = 4;
  string kind = 5;
  string source = 6;

  float confidence = 7;
  bytes payload_json = 8;
}

message ObservationBatch {
  string session_id = 1;
  repeated Observation observations = 2;

  uint32 consumed_slot_id = 3;
  uint64 consumed_generation = 4;
  string model_version = 5;
  uint32 elapsed_ms = 6;
}

service VisionWorker {
  rpc Analyze(stream FrameDescriptor) returns (stream ObservationBatch);
}
```

生产版本可以把 `payload_json` 替换为具体 oneof 类型：

```protobuf
message HealthObservation {
  uint32 health = 1;
}

message PositionObservation {
  float x = 1;
  float y = 2;
  string zone_id = 3;
  float uncertainty_radius = 4;
}
```

### 8.3 共享内存槽位规则

Rust 写入帧：

```text
slot_id
generation
frame_id
timestamp_ns
offset
length
width
height
stride
pixel_format
```

Python 读取完成后返回：

```text
consumed_slot_id
consumed_generation
```

Rust 只有收到 ACK 后才能复用该槽位。`generation` 用来避免 Python 误读已经被覆盖的旧帧。

---

## 9. 服务端 API

FastAPI 对外提供低频控制接口，不负责高频帧传输。

### 9.1 健康检查

```text
GET /health
```

### 9.2 创建 Session

```text
POST /v1/sessions
```

请求：

```json
{
  "mode": "offline_review",
  "map_id": null,
  "resolution": {
    "width": 1920,
    "height": 1080
  },
  "source": "uploaded_video"
}
```

响应：

```json
{
  "session_id": "session_20260713_001",
  "created_at": "2026-07-13T16:00:00Z"
}
```

### 9.3 上传媒体

```text
POST /v1/sessions/{session_id}/media
```

支持：

- 图片
- 录像
- 音频

响应保存原始证据层元数据。

### 9.4 触发分析

```text
POST /v1/sessions/{session_id}/analyze
```

请求：

```json
{
  "mode": "offline",
  "tasks": [
    "hud",
    "minimap",
    "killfeed"
  ],
  "time_range_ms": {
    "start": 0,
    "end": 30000
  }
}
```

### 9.5 查询时间轴

```text
GET /v1/sessions/{session_id}/timeline
```

返回 Observation 和 Decision 的混合时间轴。

### 9.6 查询状态

```text
GET /v1/sessions/{session_id}/states
GET /v1/sessions/{session_id}/states/{state_version}
```

### 9.7 人工标注

```text
POST /v1/sessions/{session_id}/annotations
```

人工标注必须以追加事件保存，不直接覆盖模型输出。

### 9.8 决策请求

```text
POST /v1/sessions/{session_id}/decisions
```

请求：

```json
{
  "trigger_timestamp_ms": 68420,
  "state_version": 1842,
  "requested_outputs": [
    "enemy_belief",
    "duel_risk",
    "recommendation"
  ],
  "max_result_age_ms": 1200
}
```

响应：

```json
{
  "request_id": "req_000923",
  "session_id": "session_001",
  "state_version": 1842,
  "status": "success",
  "recommendation": {
    "category": "avoid_duel",
    "action": "hold_and_wait_for_teammate",
    "confidence": 0.74
  },
  "enemy_risk": [
    {
      "zone_id": "a_main",
      "probability": 0.46
    }
  ],
  "duel": {
    "win_probability": 0.41,
    "lower_bound": 0.33,
    "upper_bound": 0.51,
    "confidence": 0.65
  },
  "reasons": [
    "no_trade_teammate",
    "health_disadvantage"
  ],
  "spoken_text": "不建议干拉，先等队友到位。",
  "metadata": {
    "model_version": "duel-model-0.1",
    "elapsed_ms": 186,
    "generated_at_ms": 68490
  }
}
```

---

## 10. 存储布局

第一版使用本地目录 + SQLite + JSONL。稳定后将事件和状态转为 Parquet。

```text
data/
└─ sessions/
   └─ session_20260713_001/
      ├─ manifest.json
      ├─ media/
      │  ├─ source.mp4
      │  └─ frame_000001.png
      ├─ observations/
      │  ├─ observations.jsonl
      │  └─ observations.parquet
      ├─ states/
      │  ├─ tactical_states.jsonl
      │  └─ tactical_states.parquet
      ├─ decisions/
      │  ├─ decisions.jsonl
      │  └─ decisions.parquet
      ├─ annotations/
      │  ├─ manual_labels.jsonl
      │  └─ manual_labels.parquet
      └─ logs/
         └─ analysis.log
```

SQLite 保存索引和任务状态：

```text
sessions
media_assets
analysis_jobs
model_versions
```

Parquet 保存大量时序数据：

```text
observations
trajectory_samples
state_snapshots
decision_results
manual_labels
```

---

## 11. 地图数据

地图不应该只是一张图片。需要同时维护：

```text
map image
zone polygons
navigation graph
sound connectivity
common angles
```

示例：

```json
{
  "map_id": "ascent",
  "zones": [
    {
      "zone_id": "a_main",
      "display_name": "A Main",
      "floor": 0,
      "polygon": [
        [0.51, 0.42],
        [0.57, 0.42],
        [0.57, 0.48],
        [0.51, 0.48]
      ],
      "neighbors": [
        "a_lobby",
        "a_site"
      ]
    }
  ],
  "edges": [
    {
      "source": "a_lobby",
      "target": "a_main",
      "min_travel_seconds": 2.1,
      "max_travel_seconds": 4.8,
      "sound_connectivity": 0.8
    }
  ]
}
```

坐标统一使用归一化坐标：

```text
x: 0.0 到 1.0
y: 0.0 到 1.0
```

这样不同分辨率、不同地图图片尺寸下仍能复用。

---

## 12. 状态传播

内部传播增量事件，不频繁广播完整状态。

```json
{
  "sequence": 1842,
  "timestamp_ms": 68420,
  "changes": [
    {
      "path": "player.health",
      "old_value": 100,
      "new_value": 73
    },
    {
      "path": "enemy_unknown_1.last_seen_zone",
      "old_value": null,
      "new_value": "a_main"
    }
  ]
}
```

同时定期保存完整快照：

```text
每 1 到 5 秒保存一次 TacticalState
关键事件发生时立即保存 TacticalState
```

回放任意时间点：

```text
读取最近一次 state_snapshot
  ↓
重放 snapshot 之后的 delta events
  ↓
恢复目标时间点状态
```

---

## 13. 决策模型边界

实时决策不直接让大语言模型看截图回答。

正确流程：

```text
Observation
  ↓
TacticalState
  ↓
EnemyBelief
  ↓
DuelRisk
  ↓
TacticalPolicy
  ↓
Template Explanation
```

输出必须可解释、可统计：

```text
recommended_action
confidence
reason_codes
state_version
model_version
elapsed_ms
```

建议的 reason codes：

```text
low_information
health_disadvantage
weapon_disadvantage
enemy_angle_advantage
no_trade_teammate
crossfire_risk
time_pressure
utility_available
spike_pressure
economic_risk
```

第一版允许返回：

```text
信息不足，暂不建议主动行动。
```

这是一个合法结果，不是失败。

---

## 14. 开发阶段

### Phase A：截图 MVP

目标：验证 API、文件保存、图像元数据、ROI 裁剪和结构化返回。

任务：

1. `POST /v1/sessions`
2. `POST /v1/sessions/{session_id}/media`
3. 保存图片到 `data/sessions`
4. 返回宽高、哈希、文件路径
5. 裁剪 HUD、小地图、击杀栏 ROI
6. 返回占位 Observation

验收：

```text
上传一张截图后，能在 response 和本地文件中看到稳定的结构化结果。
```

### Phase B：录像导入

目标：从视频中抽帧，生成时间轴。

任务：

1. 上传 mp4
2. 提取 fps、duration、width、height
3. 每 200ms 抽一帧
4. 写 frame index
5. 输出 observations.jsonl

验收：

```text
能打开一段录像，看到每个抽帧点的 frame_id、timestamp_ms 和 ROI 信息。
```

### Phase C：基础识别

目标：实现第一个真实识别闭环。

优先顺序：

```text
HUD 血量
HUD 弹药
小地图位置检测
击杀栏变化检测
```

验收：

```text
识别结果能以 ObservationEvent 保存，并能被人工修正。
```

### Phase D：状态聚合

目标：从 Observation 得到 TacticalState。

任务：

1. 实现 EventFusionService
2. 实现 state_version 自增
3. 实现 state_snapshot 保存
4. 实现 timeline 查询

验收：

```text
给定一串 observations，可以重建任意时间点的局面状态。
```

### Phase E：复盘 Dashboard

目标：让数据可视化，形成标注闭环。

页面：

```text
Session 列表
录像播放器
事件时间轴
地图轨迹
Observation 详情
人工修正
```

### Phase F：Rust Agent

目标：实现采集、缓存和快捷键。

任务：

1. 检测游戏窗口
2. 视频采集
3. 音频采集
4. 环形缓存
5. 快捷键固化片段
6. 上传片段到 Server

第一版 Rust 不需要和 Python 共享内存，先上传固化片段即可。

### Phase G：实时 IPC

目标：减少延迟和复制。

任务：

1. 定义 Protobuf
2. Rust 创建共享内存环形缓冲
3. Python 通过 gRPC 接收 FrameDescriptor
4. Python 返回 ObservationBatch
5. Rust/Python ACK 槽位

只有当离线识别有效后，再进入该阶段。

---

## 15. 当前下一步

基于当前仓库状态，最合适的下一步不是马上写 Rust，而是先让 Python Server 形成第一个可测闭环：

```text
FastAPI
  ↓
创建 Session
  ↓
上传图片
  ↓
保存原始图片
  ↓
计算 sha256 / width / height
  ↓
裁剪 ROI
  ↓
返回结构化 ImageAnalysisResult
```

建议先实现这些文件：

```text
server/src/app/schemas/media.py
server/src/app/storage/session_store.py
server/src/app/media/image_loader.py
server/src/app/vision/roi.py
server/src/app/api/sessions.py
server/src/app/api/media.py
```

同时创建：

```text
data/sessions/.gitkeep
shared_schema/json_schema/observation.schema.json
```

第一版完成后，再把识别结果写成 `observations.jsonl`。这会成为后续录像、复盘、标注、训练和实时 IPC 的共同基础。

