# 全屏实拍与自制动效：输入与验证

`render_fullscreen_mix.py plan.json --preview` 先查看代表帧；`render_fullscreen_mix.py plan.json` 正式导出。它不联网、不下载素材、不判断语义、不生成配音（配音用`tts_lines.py`另行生成）。输出尺寸取plan的width／height，默认576×1024；所有图形和字幕坐标都按576×1024版式写，由渲染器按比例重绘。fps取plan。

## JSON约定

顶层：reference（原片，用于复制原音轨并禁止原片画面）、audio（可选，台词重写时的新音轨，须为AAC等可直接放进MP4的编码；给了就复制它而不是原音轨，此时reference可省略）、fps、total_frames、width/height（输出像素，须9:16，交付片用1080/1920）、enhance（可选true：取景宽小于输出宽九成的实拍段加hqdn3d去噪和cas锐化，缩小的素材不处理）、caption_style（可选：默认bar底部白字，box为下三分之一黄底黑字，pop／band／paper见下文“字幕样式”）、work（新版本工作目录）、output（不存在的新输出文件）、segments、captions。字体默认Windows微软雅黑，可通过font/font_bold指定可读字体路径。

segments必须以start_frame包含、end_frame不包含的范围连续覆盖0至total_frames。每段含id和mode。

实拍mode为footage，含path、source_in（源文件秒数）、crop=[x,y,width,height]（源像素，必须9:16），可选source_span（源时长秒数，未提供时等于目标段时长）。source_span与目标时长不同时只变画面速度。默认禁止把reference路径放入实拍段；确需保留真实产品屏幕时设顶层allow_reference_pictures=true，逐段注明原因。可选accent={"labels":["跟读留存"]}按顺序轻量强调原词，不生成假界面。

自制图形mode为graphic，含scene、title、可选eyebrow。scene支持tools、book、words、topics、wave、sync、archive、records、dialog、feedback、analysis、end，以及v0.6新增：

- scorecard：score数值、可选label与parts=[[名称,值],…]，分数从0计到目标值；用于用户剧情时tag设“情景示意”。
- icons：items=[[图形,文字],…]，1—4张卡，图形可选phone、bed、bowl、clock、chat、target、chart、book，其他值画勾。
- keyword：items为1—2个关键词，全屏底色大字依次出现；可设bg、color。
- brand：品牌文字尾板，title加可选lines，只有文字，不画标志。

words/topics另需items字符串数组，可用top、gap调整起始位置和间距，让4项以上的列表避开下三分之一字幕；wave可指定label。图形右上角默认“功能示意”，可用tag改成“示意”“情景示意”，纯关键词或品牌尾板可设空字符串。新增图形都在y≈700以上，box字幕不会压住。这些是案例图形模板，不证明任何产品提供对应功能；更换产品须核对文字与业务含义。产品名不写死在渲染器里：sync用source_name、target_name，end用name，book用tags（两个标签）；任何graphic段可设header画左上角小标题，不设就不画。dialog等场景里的示例文字使用前按新任务改。

captions每条含start_frame、end_frame和text，pop／band／paper另可加emphasis（要强调的词，必须是text里原有的字）和variant。不做语音识别或字幕自动纠错，台词文本来自已核对的字幕计划。

## 字幕样式

同批片子各选一种，按片子的说话人定，不按好看定：

| caption_style | 观感 | 适合 | variant | 入场 |
|---|---|---|---|---|
| pop | 大白字粗黑描边，关键词黄色放大 | 第一人称吐槽、剧情口播 | `punch`：关键词变成微斜红贴纸，一条片子只用在2—3句点题句 | 放大回弹 |
| band | 通栏半透明底条，关键词换色 | 对家长、讲解类 | `pain`深蓝底橙字，`plan`绿底金字；把片子前半的问题和后半的方案分开 | 上移淡入 |
| paper | 米白答题卡加红笔波浪线 | 无口播、字幕就是主信息 | `left`／`right`逐句交替靠边 | 上移淡入 |

- 每句只强调1—2个词。先选句子里最有情绪或最关键的词，别选虚词；品牌名只在品牌句强调。
- 位置：两行字幕的上沿不高于y≈670，下沿不低于y≈830（再往下是平台标题区）。图形卡片定格在y≈650以内，但入场时还有约40像素下移，字幕太高会盖住卡片入场。
- 字宽超限时自动缩字号，不折行也不改字。贴纸的内边距要算进行宽，否则盖住相邻的字（2026-10-30踩过）。
- 复审要放大看贴纸句和卡片入场帧：缩略联系表看不清压字。

## 配音音色（火山seed-tts-2.0）

台词JSON：`{"engine":"volc","voice":"…","rate":18,"tone":"…","gap":0.1,"lead":0.15,"tail":0.7,"lines":[…]}`。`rate`是-50到100的语速；`tone`走context_texts，只影响语气不会被念出来。接口是V3单向HTTP（`/api/v3/tts/unidirectional`，资源ID`seed-tts-2.0`），只用App ID和Access Token，Secret Key用不上。

2026-10-30用一个只开了2.0资源的账号实测：V1接口和1.0音色（`_moon_bigtts`、`_mars_bigtts`、`BV…`）报3001未授权；`_uranus_bigtts`和`saturn_…_tob`能用。新账号先拿一句话探一遍可用音色，不要假定。下表“适合”是按音色名称和定位选的，未经人耳比较：

| 场景 | 可试音色 |
|---|---|
| 女学生口吻 | `zh_female_vv_uranus_bigtts`、`zh_female_linjianvhai_uranus_bigtts`、`zh_female_shuangkuaisisi_uranus_bigtts`、`zh_female_tianmeixiaoyuan_uranus_bigtts` |
| 男学生口吻 | `zh_male_shaonianzixin_uranus_bigtts`、`saturn_zh_male_shuanglangshaonian_tob` |
| 对家长、讲解 | `zh_female_kailangjiejie_uranus_bigtts`、`zh_female_liuchangnv_uranus_bigtts`、`zh_male_ruyayichen_uranus_bigtts`、`zh_male_m191_uranus_bigtts` |

`zh_female_zhixingnvsheng_uranus_bigtts`、`zh_male_jieshuonansheng_uranus_bigtts`报资源不匹配，不是这个资源里的音色。

例：

```json
{
  "reference": "D:/project/reference.mp4",
  "fps": 30, "total_frames": 120,
  "work": "D:/project/v2/work", "output": "D:/project/v2/result.mp4",
  "segments": [
    {"id":"V01", "mode":"footage", "start_frame":0, "end_frame":60,
     "path":"D:/project/study.mp4", "source_in":3.0, "crop":[100,0,450,800]},
    {"id":"G02", "mode":"graphic", "start_frame":60, "end_frame":120,
     "scene":"wave", "title":"听力练习", "label":"聆听与跟读"}
  ],
  "captions":[{"start_frame":0,"end_frame":120,"text":"此处填写已确认的原句"}]
}
```

## 验证边界

工具输出verification.json：源文件sha256不变、计划音轨（原音轨或audio）与成片音轨解码PCM一致（audio_source、audio_replaces_reference记录用的是哪条）、目标帧数、完整解码、实拍／全屏图形／文字强调帧数、原片画面直接引用帧数。源文件相同的画面可能另有镜头内容重复，工具不判断视觉相似度或素材授权。

人工视觉复核：每段起／中／尾有无旧字幕露出、主体裁断、跨到新场景、黑边或模糊填边；连续观看声画节奏、字幕时机和动效停留。抽样检查须注明抽样，不声称逐帧或人工全片核听。功能示意不能代替真实产品功能证据；服务未确认继续记录。
