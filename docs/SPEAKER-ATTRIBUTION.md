# Speaker attribution without voice enrolment — investigation (2026-10-16)

**Question.** How can the pipeline tell who said each line of a Teams meeting, by name, without a voice-identification model? People change from meeting to meeting, so a voiceprint database per person is out.

**Short answer.** The Teams client already knows who is speaking at every moment (the service sends it an active/dominant-speaker list, which it renders as the speaking indicator, the live captions and the transcript), but it writes none of it to disk. The only way to read that knowledge from outside the client without Microsoft's cloud is the macOS Accessibility API on the Teams window (option A), which needs one spike during a real call. Two things need no Teams data at all and can be done now: the user's own lines are already on their own track (option B), and a per-meeting clustering of voices needs no enrolment (option C). Microsoft's own speaker-attributed transcript (option E) is the best source where the tenant allows it, and the right ground truth to measure A and C against.

## 1. What the pipeline has today

- `teams-tap` records Teams' output as one **stereo mixdown** of the Teams processes (`capture.log`: `tap format 48000 Hz, 2 channel(s)`; on 2026-10-14 it captured the ModuleHost and three WebView helpers). Every remote participant arrives already mixed by Teams; there is no per-participant stream to tap.
- The microphone is a **separate track** (`mic.wav`), so the user's voice is already separated from everyone else's.
- Both tracks are aligned to the meeting's start instant (`--epoch`), so an outside timeline of wall-clock events can be mapped onto transcript seconds.
- `StopRecording.finalize` mixes both tracks to mono `audio.m4a` and **deletes the raw tracks**. whisper runs on the mix with `-mc 0`; `Segment` has `start`, `end`, `text` and no speaker. `prompts/analyze_system.md` says "There is no speaker identification" and asks the model to infer owners from first/third person and from names addressed.
- The cost of the gap is measured: of 57 wrong analysis claims in `docs/tasks/prd-llm-wiki/evaluation.md` §14.2, 22 had the wrong owner and 14 listed as a participant someone who was only mentioned; owner errors propagate to every following daily plan.

## 2. Where the information exists

| Source | What it has | Reachable from this Mac? |
|---|---|---|
| Teams client (new Teams 26261.303, `com.microsoft.teams2`: WebView2 on Edge 154 + the native `ModuleHost` running SlimCore) | The calling stack raises `CallHandlerOnDominantSpeakerListChanged` / `CallHandlerOnActiveSpeakerListChanged` with `dominantSpeakerInfo`, `speakerList`, `ParticipantIsActiveSpeaker`, `ParticipantDominantSpeakerRank` (`Contents/Resources/client-bindings/calling_electron_bundle.js`); the web app keeps `isSpeaking`, `isSpeakingTracker`, `activeSpeakerManager` and an `AnnounceActiveSpeaker` accessibility feature behind the flag `enableAnnounceActiveSpeaker`, plus `aria-live` regions (cached app code under `EBWebView/WV2Profile_tfw`) | Only through the UI: the client **does not log it**. The `MSTeams_*.log` files in `~/Library/Group Containers/UBF8T346G9.com.microsoft.teams/Library/Application Support/Logs` have zero lines about dominant or active speakers; the only hits are inside `sc-tfw/slimcore-aria-cache.data`, a telemetry cache |
| Microphone track | The user's voice, nothing else | Yes, already recorded |
| Stereo channels of the Teams track | A left/right position per participant **only when Teams' spatial audio is on** | Yes, already recorded as 2 channels; the mixer throws it away |
| Microsoft 365 | The meeting transcript with `<v Name>` voice tags (Graph), or per-participant raw audio for a bot | Tenant policy and admin consent decide |

## 3. Options

### A. Read the Teams UI through the macOS Accessibility API — recommended spike

**Idea.** A small Swift helper (a sibling of `teams-tap`, spawned per recording) asks Teams for its accessibility tree and watches the meeting window: the participant tiles and the roster carry each person's display name and their speaking/muted state; the live captions pane, when the user turns it on, carries `name + text`. The helper appends `(wall-clock, name, speaking)` events to `speakers.jsonl` in the meeting folder, together with the roster (every name seen) and the window title (the meeting subject, which would fill `Meeting.title`, today manual). Afterwards, in code, each transcript segment maps to a wall-clock interval through the epoch and takes the name that was speaking in it; the microphone energy (option B) decides "the user" first.

**Why it fits.** No model and no enrolment; the names are Teams' own display names; nothing leaves the Mac; it works in Portuguese; a person who appears once is handled like any other. Windows has the same tree through UI Automation, with no permission.

**Mechanics.** Chromium builds the accessibility tree of web content only when an assistive client announces itself, by setting `AXEnhancedUserInterface` on the app (what VoiceOver does; Electron also honours `AXManualAccessibility`, and Chromium has `--force-renderer-accessibility`). The helper needs the **Accessibility** permission (TCC), granted to the helper itself: the same embedded-`Info.plist` trick that gives `teams-tap` its identity for Screen & System Audio Recording, with its own bundle id. Chromium's accessibility mode costs Teams some memory while the helper is attached.

**Risks.** The labels are UI strings of a product that updates itself (risk R3's family): isolate the helper behind a port and fail soft, so a missing or unreadable tree leaves today's behaviour. The indicator is coarse: Teams marks a speaker with some latency and only a few speakers at once, so overlapping speech and very short turns will be mislabelled; the transcript segment granularity (whisper's lines) is the unit, not the word. Whether the tree is kept for a minimised or occluded meeting window is unknown.

**Verified on 2026-10-16 (run 1, a test meeting with nobody else; see §6).** The web content is exposed through the Accessibility API: 3 `AXWebArea` and 293 elements across the two Teams windows, even though Teams answers `kAXErrorNotImplemented` (-25208) when asked to set `AXEnhancedUserInterface`; Chromium turns its web accessibility on as soon as a client reads the tree. The participant tile is an `AXImage` whose description reads `Vídeo de mim mesmo, Felipe Mateus de Carvalho, Mudo desativado, Tem menu de contexto`: the name and the mute state are plain text, in the UI language, and the description changed during the call, so polling sees state changes. The meeting window's title starts with the meeting subject. **Still unverified:** whether a speaking state is text too (nobody else was in that call), what another participant's tile and the roster entries say, and the captions lines. `scripts/ax-speaker-probe.swift` is the spike: run it during a real call where someone else talks (see its header). Run 7 (§6), with a colleague in the meeting, found the likely speaking indicator: the tile's frame element gaining the `vdi-frame-occlusion` class set, with a text alternative in the compact view's active-speaker mode; the probe's `--watch` mode, which logs every transition, confirms or refutes it.

### B. "You" against "others" from the two tracks — no dependency, do first

Per transcript segment, compare the energy of `mic.wav` and `tap.wav` over `[start, end]`: the microphone wins → the user said it; the Teams track wins → someone else did. This is a few lines of code with no model and no Teams data. The raw tracks are deleted at `finalize`, so either transcribe before deleting (the transcription already converts the mix to 16 kHz WAV) or, cheaper, write an energy timeline per track (one value per 100 ms, a small JSON) at `finalize` and label later. It removes the first-person heuristic from the prompt and turns the user's commitments ("eu faço", "pode deixar comigo") into labelled lines; by itself it does not name the other speakers.

### C. Unsupervised diarization — clustering, not identification

A diarization pipeline (speech segmentation → speaker embeddings → clustering) splits a meeting into turns labelled `SPEAKER_00…N` with **no enrolment and no database**: the labels are per meeting and anonymous. It still runs a neural model, but not one that knows anybody. Names then come from option A (each cluster takes the name that was speaking most while it spoke) or from the model's context (self-introductions, people addressed); even anonymous turns help the analyser, which can see that the person who took a task is the one who later gave a deadline.

Candidates that fit this Mac (an Apple Silicon MacBook Air with tight memory, where the `anthropic` SDK import alone was a problem):

- **sherpa-onnx**: ONNX on the CPU, Python wheel or Swift; `sherpa-onnx-pyannote-segmentation-3-0` for segmentation plus a 3D-Speaker, NeMo or WeSpeaker embedding model; clustering by a threshold, with an optional fixed number of speakers.
- **FluidAudio**: a Swift package running Pyannote on Core ML and the Neural Engine, macOS 14+, Apple Silicon only; about 15% diarization error rate offline in its own benchmark. Its streaming Sortformer model is limited to four speakers.
- **pyannote.audio** itself needs PyTorch: heavier than this Mac tolerates in the daemon.
- **whisper.cpp tinydiarize** (`-tdrz`) is English-only: no.

Costs: minutes of extra CPU per meeting; 10–20% of the time attributed to the wrong cluster, worse on overlapping speech; the hallucination-loop guard would need to understand labels.

### D. Stereo position with Teams' spatial audio — a cue, not identification

Teams can place each participant's voice where their video tile is. Requirements, from Microsoft's support page: USB-wired stereo headphones or speakers or the device's built-in stereo speakers (**no Bluetooth**), more than two participants in gallery view, not for one-on-one calls or meetings over 100 attendees, and Teams turns it off under low bandwidth or memory. The current default output on this Mac is the built-in speakers (2 channels), so it would apply when the user turns the setting on.

The tap already records both channels; the mixer downmixes to mono, so the Teams track would have to stay stereo and be transcribed apart from the microphone. whisper.cpp's `--diarize` labels each segment by the louder channel: verified locally with two synthetic Portuguese voices on separate channels (`say`, voices Eddy and Flo), which came back as `(speaker 0)` and `(speaker 1)` with a `speaker` field in the JSON, 14 s of audio in 3.8 s. For more than two people a pan-angle clustering per segment would be needed (plain DSP). It is zero-model but fragile: positions follow the gallery and move when it re-sorts, a Bluetooth headset switches the feature off, and it gives positions, not names. Worth an experiment only if A fails.

### E. Teams' own transcript, speaker-attributed

Teams transcription records "who is speaking and when" and stores the transcript in OneDrive/SharePoint next to the recording; Portuguese (Brazil) is supported. Conditions:

- Policy: transcription is a per-organizer and per-user setting (`Set-CsTeamsMeetingPolicy -AllowTranscription`, on by default for new policies); the organizer and whoever starts it must have it. Turning off Copilot for a meeting also turns off recording and transcription.
- Someone must start transcription (or Copilot) in the meeting, which every participant sees: a different footing from today's private recording.
- Graph: `GET /me/onlineMeetings/{id}/transcripts/{id}/content` returns `text/vtt` with `<v Speaker>` tags. Delegated permission `OnlineMeetingTranscript.Read.All` **requires admin consent**; personal accounts are not supported; application permission also needs an application access policy. Two independent tenant controls can block it (`GraphAccessToTranscriptsDisabled`, `SpeakerAttributionNotAllowed`), and the API works only while the meeting has not expired. The `.docx` format is deprecated.
- Manual variant with no app registration: download the `.vtt` from the meeting recap and import it.

The PRD notes native recording may be disabled in this tenant, so availability has to be checked once: whether "Start transcription" appears in a meeting's "More" menu. Where it exists, it is the best source of truth, and the right reference to measure A and C against even if the pipeline never depends on it.

### F. Graph real-time media bot — correct, out of scale

An application-hosted media bot receives each participant's audio unmixed with the speaker's id (`Calls.AccessMedia.All`, admin consent, an Azure-hosted bot that visibly joins every meeting). Azure Communication Services interop does not expose per-participant audio. It is the official way to get what the tap cannot, and far beyond a personal background tool.

### Rejected

- Reading the SlimCore ↔ web app channel (`--native_msg_channel`) or the WebView's remote debugging: undocumented, fragile and indistinguishable from tampering with the client.
- Voice identification with a voiceprint per colleague: the premise of the question.

## 4. Recommendation

1. **B now**: label the user's lines from the two tracks (energy timeline at `finalize`, labels at transcription), update the prompt, show the label in `transcript.txt` and the minutes.
2. **Spike A again on the next real call where someone else talks**, with `scripts/ax-speaker-probe.swift` (run 1 confirmed the names and the mute state on the tiles; the speaking state is pending, see §6). If it is text too, implement it: a `SpeakerObserver` port, a Swift helper with its own TCC identity, `Segment.speaker`, `Transcript.as_timestamped_text` with names (`[HH:MM:SS] Nome: texto`), the roster and the window title fed to the analysis, a `trec doctor` line for the permission, and the prompt rules for owners rewritten around labels. If the tree exposes nothing usable, fall back to C as an optional step (sherpa-onnx or FluidAudio), with A's failure recorded here.
3. **Check E once**: if transcription is available in the tenant, keep it as the evaluation reference for A and C, and consider importing it when the user chooses to start it.

## 5. Changes implied

- `domain`: `Segment.speaker: str | None` (the codec reads old transcripts without it); `Transcript.as_timestamped_text` with names; `Meeting.participants_seen` or the roster in `meta.json`.
- `application/ports.py`: `SpeakerObserver` (start/stop per recording → `speakers.jsonl`); an energy reader for option B.
- `adapters/outbound`: `speakers_ax` (macOS helper) and later `speakers_uia` (Windows); the energy timeline through ffmpeg or the WAV reader.
- Use cases: `StopRecording.finalize` writes the energy timeline before deleting the tracks; `TranscribeMeeting` labels segments from `speakers.jsonl` and the timeline.
- Prompts and renderers: labels in the transcript given to the analyser and the verifier; owners taken from labels; the minutes show who said what.
- `prd/README.md` §6 still says diarization is out of scope; it changes when B lands.

## 6. Spike runs

### Run 1 — 2026-10-16 23:04, test meeting, the user alone, 120 s

- Accessibility permission granted to the terminal; `AXEnhancedUserInterface` → -25208 (`kAXErrorNotImplemented`), tree readable anyway: 293 elements in the first pass (AXGroup 206, AXButton 36, AXPopUpButton 11, AXCheckBox 8, AXStaticText 8, AXImage 6, AXWebArea 3, AXTable 1).
- Windows: `Calendar | <organisation> | <account> | Microsoft Teams` and `tb | <organisation> | <account> | Microsoft Teams`, `tb` being the test meeting's subject: the title carries the meeting name.
- Call texts: `Aguardando o ingresso de outros participantes...`, the button `Ativar mudo do microfone`, the tile `Vídeo de mim mesmo, Mudo desativado, Tem menu de contexto`, which later read `Vídeo de mim mesmo, Felipe Mateus de Carvalho, Mudo desativado, Tem menu de contexto`.
- Noise: the keyword filter also matched chat rows and one chat message in the Calendar window (`Mudo ativado` there is a muted chat; `Participantes:` was inside a message). The probe now logs only windows that look like a call (a tile, the waiting message or the leave button), skips table rows and texts over 200 characters, and `--window` picks a window by its title.
- Open: the speaking state, the remote tiles, the roster entries, the captions lines. Next run: a real meeting with at least one other speaker, 3 to 5 minutes with the default filter, then one minute with `--all` while live captions are on, to see the captions pane.
- Privacy: run 1's log holds a chat message. It lives in `data/log/`, which git ignores; delete it once read.

### Run 2 — 2026-10-16 23:06, one-to-one call that was not answered, 120 s, first version of the probe

- The call window's title starts with the other person's name (a meeting's starts with its subject, run 1).
- Mute toggled twice by the user: the button went `Ativar mudo do microfone` → `Desativar mudo do microfone`, the own tile went `Mudo desativado` → `Mudo ativado`, and an `AXStaticText` announcement appeared each time (`O microfone está com o mudo ativado`, `O microfone está com mudo ativado`, `O microfone está com o mudo desativado`): Teams exposes its live-region announcements as text, and a state change showed up within one polling interval (under a second).
- No text for the other participant: the call was still ringing, so nothing about remote tiles or speaking yet. The first version only logged texts with state words; the current one logs every tile (`Vídeo de …`), so a remote tile will appear whatever its state.
- Still open, as after run 1: speaking state, remote tiles, roster, captions. A real meeting with someone else talking is needed.

### Run 3 — 2026-10-16 23:08, the same unanswered call, 120 s, current probe

- The call-window detection works: the call window was logged, the chat window skipped; only the mute button and the own tile were logged (2 texts, 932 elements in the first pass), no chat content.
- Still nothing remote, since nobody answered. A way to test without waiting for a meeting: join a test meeting from a phone with the Teams app as a second participant and talk into the phone; the phone's tile and its speaking state, if it is text, then show up in the log.

### Runs 4 to 6 — 2026-10-16 23:12 to 23:24

- Run 4 (300 s, the unanswered call again): the mute button and the own tile only.
- Run 5 (180 s, the meeting `teste sonda` with a second participant joined from a phone, default filter): four windows, among them `Modo de exibição compacto da reunião | teste sonda | …` (the floating compact view) and the meeting window, detected as the call window. Only the mute button was logged: with two people, nothing carries the words of the one-person layout, not even the own tile.
- Run 6 (60 s, the same meeting, `--all`): 32 texts, all from the first pass: the call indicators (`Status da criptografia`, `Tempo decorrido 00:03`, `00:17`), the meeting controls (`Chat`, `Pessoas`, `Levantar`, `Reagir`, `Exibição`, `Controles`, `Anotações`, `Salas`, `Aplicativos`, `Mais`, `Ativar câmera`, `Ativar mudo do microfone`, `Compartilhar`, `Sair`, `Mais opções`) and the stage, a group named `Exibição de conteúdo compartilhado` holding one `AXStaticText` with the other participant's name and nothing else. **Nothing changed in 93 passes, not even the timer:** Blink updates its accessibility tree inside the rendering lifecycle, and a window fully covered by the terminal is not rendered, so its tree freezes. In run 2 the user was clicking in the Teams window, which is why the mute changes showed.
- Lessons: the remote tile's accessible text is the bare name, so the speaking state, if exposed at all, must be in DOM classes or ids (`AXDOMClassList`, `AXDOMIdentifier`), which Chromium serialises only in screen-reader mode; the probe's `--tree` mode dumps them and tries the screen-reader switch on the window. The call window must stay visible while observed; the compact view, which Teams keeps on top when the meeting loses focus, now counts as a call window. The helper, if built, has the same constraint: a covered Teams window stops reporting.

### Run 7 — 2026-10-16 23:28, meeting `teste sonda`, the user plus a colleague on another device, 90 s, `--tree`, window visible

- The tree was live: the timer text changed every second, which confirms that run 6's frozen tree came from the covered window.
- DOM ids and classes are exposed without the screen-reader switch (176 of 207 logged elements). Ids are semantic (`#indicators`, `#call-duration-custom`, `#microphone-button`, `#roster-button`, `#hangup-button`, `#view-mode-button`); classes are mostly Fluent UI / Griffel atomic hashes (`f22iagw`, `___1hpaaze`), with a few readable ones (`vdi-occlusion`, `vdi-dynamic-occlusion`, `vdi-frame-occlusion`, `lpcCommonWeb-hoverTarget`, `fui-AriaLive__assertive`, `fui-AriaLive__polite`).
- The stage is an `AXLandmarkMain` named `Exibição de conteúdo compartilhado`. The own tile is an `AXImage` `Vídeo de mim mesmo, <user>, Tem controle das ferramentas de produção, Mudo desativado, Tem menu de contexto` (`.vdi-dynamic-occlusion`). A remote tile is an `AXMenuItem` `<name>, Tem controle das ferramentas de produção, O menu de contexto está disponível` holding an avatar group (`.bkg_<hash>`), the name as `AXStaticText` under `.lpcCommonWeb-hoverTarget`, and, as its last child, an empty `fui-Flex` group: the tile's frame. The remote tile carries no mute or speaking words.
- **The frame has two class sets.** One has `vdi-frame-occlusion` and eight more atomic classes (`f14rmoke ftevtku f1qyaz97 fm03cl5 f3ve9t9 frwhdur fn8mz29 f1ky4vpe`, Griffel hash `___1vvhwjq`); the other lacks them and has `f1429bq1 f9pox2d` instead (`___dv8x4j0`). At dump time the compact window's tile had the frame and the main window's did not; at 23:28:35 the compact window's frame went away. Hypothesis: the frame is the speaking border. The probe's new `--watch` mode logs every transition by element path with the classes added and removed, so a test with the colleague talking in 10 s bursts while the user stays muted settles it.
- The compact view has the toggles `Mostrar somente alto-falante ativo` and `Mostrar mais pessoas`. In the first mode its single tile is the active speaker: a text signal (the name) that needs no class decoding, in a window Teams keeps on top when the meeting window loses focus.

### Run 8 — 2026-10-16 23:34, `--watch`, the user muted, the colleague talking in two bursts of about 10 s

- **The speaking indicator is confirmed.** Twelve transitions in 115 s, all on the same element: the frame group of the colleague's tile in the compact window (last child of the tile's `AXMenuItem`), alternating between the class set with `vdi-frame-occlusion` (`___1vvhwjq`, `f14rmoke ftevtku f1qyaz97 fm03cl5 f3ve9t9 frwhdur fn8mz29 f1ky4vpe`) and the set without it (`___dv8x4j0`, `f1429bq1 f9pox2d`). The frame was on from 23:34:58 to 23:35:01, 23:35:09 to 23:35:19, 23:35:21 to 23:35:22, 23:35:32 to 23:35:53, 23:36:31 to 23:36:33 and from 23:36:45 to the end of the run: long stretches for the bursts, short blips for the "started" / "stopped" cues. Resolution: one pass every 0.5 to 1 s.
- Nothing changed in the main meeting window during the run; whether it was covered or whether its gallery tiles mark speaking differently is the next question, together with how the indicator behaves with two remote speakers (a third participant joined from a phone).
- What this gives the pipeline: a `(wall-clock, participant name, speaking on/off)` stream read from the tile whose name sits in the `AXStaticText` under `.lpcCommonWeb-hoverTarget`, with no model and no enrolment, as long as a Teams window with tiles stays rendered.

## Sources

- [Spatial audio in Microsoft Teams meetings](https://support.microsoft.com/en-us/teams/meetings/spatial-audio-in-microsoft-teams-meetings) and [Follow conversations with ease using Spatial Audio](https://techcommunity.microsoft.com/blog/microsoftteamsblog/follow-conversations-with-ease-using-spatial-audio-in-microsoft-teams/3888524)
- [Get callTranscript (Graph)](https://learn.microsoft.com/en-us/graph/api/calltranscript-get), [List transcripts](https://learn.microsoft.com/en-us/graph/api/onlinemeeting-list-transcripts), [OnlineMeetingTranscript.Read.All consent](https://graphpermissions.merill.net/permission/OnlineMeetingTranscript.Read.All)
- [Admins: manage transcription and captions for Teams meetings](https://learn.microsoft.com/en-us/microsoftteams/meeting-transcription-captions); [live captions with speaker attribution](https://www.uctoday.com/event-news/an-important-accessibility-feature-for-teams-live-captions-with-speaker-attribution/)
- [Chromium accessibility design](https://chromium.org/developers/design-documents/accessibility) and the [Sonoma a11y detection change](https://chromium.googlesource.com/chromium/src/+/34d5b59a67da7b0ea1a3eb90835467eb63e7262e)
- [sherpa-onnx speaker diarization](https://k2-fsa.github.io/sherpa/onnx/speaker-diarization/index.html) and its [configuration described by LocalAI](https://localai.io/docs/features/audio-diarization/); [FluidAudio offline pipeline](https://docs.fluidinference.com/diarization/offline-pipeline)
- [Cloud communications media (Graph)](https://learn.microsoft.com/en-us/graph/cloud-communications-media), [unmixed audio buffers in the comms samples](https://github.com/microsoftgraph/microsoft-graph-comms-samples/issues/431), [Q&A on per-participant audio](https://learn.microsoft.com/en-us/answers/questions/5589626/can-i-build-a-real-time-voice-interview-bot-for-te)
