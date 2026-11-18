# 交付前审计闭环

用`scripts/audit_video_delivery.py`执行真实检查，不只填写一份清单。依赖Python、Pillow、NumPy、ffmpeg、ffprobe及同目录render_fullscreen_mix.py。预览尺寸跟随plan的width／height，须是该渲染器支持的9:16画布。

## 规则与源素材登记

audit-registry.json包含assets和可选baseline_plan。每个asset含path、sha256、families；families元素为start、end（源秒数）和family（动作／机位观察标记）。重复动作或同一组机位跨不同裁切保留同一family；镜头族来自看片观察，不能按成片段落编号任意生成。

口播主播镜头可在family元素加`"a_roll":true`：审计允许它离开后再返回，但同源后一段的入点必须不早于前一段的出点，回退记“口播主镜头源时间回退”拦截，向前返回记警告并要求视觉复审写明口型同步。只标口型与成片音轨同一时刻的主播镜头。

brand_boxes为品牌像素包围区数组，每个元素有box=[x,y,w,h]、label，可选start/end限定源时间。裁切与品牌区域只能完整包含或完全不相交。包围区要覆盖小字，品牌出现位置变化时分时段标注；静态包围区不能代替检查所有移动文字。

forbidden_boxes格式相同，任何相交均拦截，适合源底字幕、作息大字与无关贴纸；仅在存在的时间内登记，不能靠删除真实有问题的区域登记来放行。包围区从实帧观察，视觉检查发现漏标要补登记并重审。

baseline_plan取已确认的字幕和时间轴，审计禁止悄悄改动。通用工具不代替服务事实核验。

## 执行与自修

1. `audit_video_delivery.py plan.json registry.json audit/prepare-01 --stage prepare`：验证源文件与取景、区间复用、非连续的镜头族复用；输出每段入／中／尾3帧联系表及相似候选。若blocked，先修正或换镜头，再用新目录重审。每段首尾也看，不能只看中点。
2. 代理视觉检查联系表，必要时看全尺寸图或连续片段；发现半个logo、源字幕、奇怪装饰、重复构图、主体裁断或不自然，先调整，重做准备检查。准备通过仅允许进入导出，不允许宣称可交付。
3. 准备审计的audit.json里status为ready_for_export_and_review才导出；用脚本串联时按这个字符串判断，不要只grep到“status”就继续。用新work目录和新输出名渲染，复制计划音轨（参考音轨，或台词重写时的audio）。保留旧版。渲染器产生verification.json，记录实际文件哈希、源哈希、解码音轨一致、帧数与解码结果。
4. `audit_video_delivery.py plan.json registry.json audit/final-scan --stage final`：对实际成片核验并抽取起中尾帧。此时因没有视觉复审结果而blocked是预期；代理要检查本轮真实导出图，不拿准备预览当导出证据。
5. 写visual-review.json（见下），逐段写实际观察。相似候选要逐对判断：重复就换镜头并回到步骤1；不同界面／动作可说明依据后记distinct。源区间重叠与返回镜头族不由文字说明豁免，修改计划解决。
6. `audit_video_delivery.py plan.json registry.json audit/final-gate --stage final --review visual-review.json --no-previews`：重新验证实际文件、绑定证据和视觉结论，只在delivery_allowed=true时交付。--no-previews仅复用已绑定同一文件的实际抽帧证据，不能跳过视觉复审。

连续同一镜头族允许按字幕分成多个段落，源时间仍须单向推进且不重叠；离开后再次返回同一镜头族会拦截（标了a_roll的口播主镜头向前返回除外）。感知相似只是补充候选，未报警不证明绝无重复；视觉要看整体反复感，不能只满足时间区间不重叠。

审计出问题后由代理在授权范围内自行修正并重审；同一方式反复失败应换素材或策略，不继续循环盲裁。缺素材不能靠重复填满。若确实无法满足，明确未满足项和补拍需求，不把未通过版当成合格交付。

## 视觉结果格式

```json
{
  "plan_sha256": "当前计划文件SHA256",
  "output_sha256": "当前视频SHA256",
  "evidence_audit": "D:/project/audit/final-scan/audit.json",
  "checks": {
    "branding":"pass", "source_captions":"pass", "subject_framing":"pass",
    "repetition":"pass", "naturalness":"pass"
  },
  "segments":[{"id":"V01","status":"pass","observations":"根据本段实际入中尾图记录观察，不写空泛通过"}],
  "similarity_dispositions":[{"pair":["V02","V04"],"decision":"distinct","reason":"实际观察到的差异"}]
}
```

segments覆盖全部镜头；无相似候选时similarity_dispositions用空数组。记录抽样范围，不能把93帧抽样写成1749帧逐帧审片。最终机器门槛通过仍不等于产品／服务事实、素材发布范围或获客效果已验证。

验证审计工具本身时，至少让一个真实失败基线被拦截，并确认修正版通过；检查没有视觉复审与过期结论不能放行。保留这些证据，不能仅运行一次好样本就声称能拦截错误。
