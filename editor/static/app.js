import {createApp, ref, reactive, computed, watch, onMounted, nextTick} from 'https://cdn.jsdelivr.net/npm/vue@3.5.43/dist/vue.esm-browser.prod.js'
import WaveSurfer from 'https://cdn.jsdelivr.net/npm/wavesurfer.js@7.12.12/dist/wavesurfer.esm.js'
import RegionsPlugin from 'https://cdn.jsdelivr.net/npm/wavesurfer.js@7.12.12/dist/plugins/regions.esm.js'
import TimelinePlugin from 'https://cdn.jsdelivr.net/npm/wavesurfer.js@7.12.12/dist/plugins/timeline.esm.js'

const STAGES = [
    {stage: 'incoming', label: 'incoming', hint: 'Not converted yet (no lb_ prefix)'},
    {stage: 'unsplit', label: 'not split', hint: 'Not split into phrases'},
    {stage: 'no_text', label: 'no text', hint: 'Some phrases are not transcribed'},
    {stage: 'no_furigana', label: 'no furigana', hint: 'Some phrases have no furigana'},
    {stage: 'done', label: 'done', hint: 'Fully processed'},
]

async function api(path, method = 'GET', body = undefined) {
    const response = await fetch(path, {
        method,
        headers: body === undefined ? {} : {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body),
    })
    if (!response.ok) {
        const detail = await response.json().then(d => d.detail, () => response.statusText)
        throw new Error(`${response.status}: ${detail}`)
    }
    return response.json()
}

const enc = encodeURIComponent

function escapeHtml(text) {
    return text.replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]))
}

// [漢字](かんじ) -> <ruby>
function rubyHtml(text) {
    return escapeHtml(text).replace(/\[([^\[\]]+)\]\(([^()]+)\)/g, '<ruby>$1<rt>$2</rt></ruby>')
}

// [漢字](かんじ) -> 漢字
function plainOf(text) {
    return text.replace(/\[([^\[\]]+)\]\(([^()]+)\)/g, '$1')
}

// what the AI correction changed: common text as it is, removed in <del>, added in <ins>
const diffCache = new Map()

function diffHtml(before, after) {
    const key = before + '\u0000' + after
    if (diffCache.has(key)) return diffCache.get(key)

    const a = [...before], b = [...after]
    // longest common subsequence, by characters
    const lcs = Array.from({length: a.length + 1}, () => new Uint16Array(b.length + 1))
    for (let i = a.length - 1; i >= 0; i--) {
        for (let j = b.length - 1; j >= 0; j--) {
            lcs[i][j] = a[i] === b[j] ? lcs[i + 1][j + 1] + 1 : Math.max(lcs[i + 1][j], lcs[i][j + 1])
        }
    }

    const parts = []
    const push = (tag, ch) => {
        const last = parts[parts.length - 1]
        if (last && last.tag === tag) last.text += ch
        else parts.push({tag, text: ch})
    }
    let i = 0, j = 0
    while (i < a.length || j < b.length) {
        if (i < a.length && j < b.length && a[i] === b[j]) push('', a[i++]), j++
        else if (j < b.length && (i === a.length || lcs[i][j + 1] >= lcs[i + 1][j])) push('ins', b[j++])
        else push('del', a[i++])
    }
    const html = parts.map(p => p.tag ? `<${p.tag}>${escapeHtml(p.text)}</${p.tag}>` : escapeHtml(p.text)).join('')
    diffCache.set(key, html)
    return html
}

function plainText(segment) {
    // some old files have the markup in original_text too
    return plainOf(segment.original_text !== undefined ? segment.original_text : (segment.text || ''))
}

function wasChanged(segment) {
    return segment.raw_text !== undefined && segment.raw_text !== plainText(segment)
}

function fmtDate(iso) {
    const d = new Date(iso)
    const pad = n => String(n).padStart(2, '0')
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

function fmtTime(seconds, precise = false) {
    seconds = seconds || 0
    const m = Math.floor(seconds / 60)
    const s = seconds - m * 60
    return `${m}:${precise ? s.toFixed(2).padStart(5, '0') : String(Math.floor(s)).padStart(2, '0')}`
}

function cssVar(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim()
}

createApp({
    setup() {
        const codes = ref([])
        const sourcePath = ref('')
        const code = ref('')
        const files = ref([])
        const filter = ref('')
        const stageFilter = ref('')
        const current = ref(null)
        const error = ref('')

        const waveEl = ref(null)
        const waveLoading = ref(false)
        const playing = ref(false)
        const time = ref(0)
        const duration = ref(0)
        const zoom = ref(0)
        const rate = ref(1)
        const stopAtEnd = ref(true)
        const activeIndex = ref(-1)
        const segmentEls = ref([])

        const busy = ref(false)
        const cursorIndex = ref(-1)  // the segment that has the cursor strictly inside
        const editIndex = ref(-1)
        const editInput = ref(null)
        const draft = reactive({text: '', original_text: null})
        const armedDelete = ref(-1)
        const historyOpen = ref(false)
        const backups = ref([])

        const jobs = ref([])
        const jobsOpen = ref(false)
        const logJobId = ref(null)
        const logEl = ref(null)
        const fakeAi = ref(false)
        const upload = reactive({open: false, preflight: null, armed: false})
        const splitDefaults = ref({min_silence_len: 800, padding: 200, silence_thresh: -40})
        // index < 0: the whole file, otherwise only that segment; pieces: the preview drawn on the wave
        const split = reactive({open: false, index: -1, min_silence_len: 800, padding: 200, silence_thresh: -40, pieces: null, note: ''})

        // wavesurfer objects are kept out of Vue reactivity
        let wave = null
        let regions = null
        let stopAt = null
        let lastSecond = -1
        let armedTimer = null
        let previewTimer = null
        let previewSerial = 0

        const stageChips = computed(() => STAGES.map(s => ({
            ...s, count: files.value.filter(f => f.stage === s.stage).length,
        })).filter(s => s.count))

        const visibleFiles = computed(() => {
            const needle = filter.value.trim().toLowerCase()
            return files.value.filter(f =>
                (!stageFilter.value || f.stage === stageFilter.value) &&
                (!needle || f.name.toLowerCase().includes(needle) || f.title.toLowerCase().includes(needle)))
        })

        const locked = computed(() => busy.value || !!(current.value && current.value.busy))
        const plainCount = computed(() => current.value ? current.value.segments.filter(s => s.text && s.original_text === undefined).length : 0)
        const uncorrectedCount = computed(() => current.value ? current.value.segments.filter(s => s.text && s.raw_text === undefined).length : 0)
        const staleCount = computed(() => files.value.filter(f => f.index_stale).length)
        const codeBusy = computed(() => jobs.value.some(j => j.code === code.value && !j.name && isActive(j)))
        const canApplySplit = computed(() => split.pieces && split.pieces.length >= (split.index < 0 ? 1 : 2))

        const activeJobs = computed(() => jobs.value.filter(isActive))
        const jobsNewestFirst = computed(() => [...jobs.value].reverse())
        const jobsSummary = computed(() => {
            const running = jobs.value.filter(j => j.status === 'running').length
            const queued = jobs.value.filter(j => j.status === 'queued').length
            const failed = jobs.value.filter(j => j.status === 'failed').length
            return [running && `${running} running`, queued && `${queued} queued`, failed && `${failed} failed`]
                .filter(Boolean).join(', ') || 'all done'
        })
        const logText = computed(() => {
            const job = jobs.value.find(j => j.id === logJobId.value)
            if (!job) return 'Pick a job to see its log'
            return [...(job.log || []), job.error ? `ERROR: ${job.error}` : ''].join('\n')
        })

        // ---- upload wizard: its state is the state of the last upload_dry / upload job ----

        const UPLOAD_KINDS = ['upload_dry', 'upload']
        const WARNING_LABELS = {incoming: 'incoming', unsplit: 'not split', no_text: 'no text', no_furigana: 'no furigana'}

        const uploadJob = computed(() => [...jobs.value].reverse().find(j => UPLOAD_KINDS.includes(j.kind)) || null)
        const uploadRunning = computed(() => !!uploadJob.value && isActive(uploadJob.value))
        const uploadDone = computed(() => !!uploadJob.value && uploadJob.value.kind === 'upload' && !isActive(uploadJob.value))
        const dryRun = computed(() => uploadJob.value && uploadJob.value.kind === 'upload_dry' && !isActive(uploadJob.value) ? uploadJob.value : null)
        const canUpload = computed(() => !!dryRun.value && dryRun.value.status === 'done' && !staleCodes.value.length
            && !(upload.preflight && upload.preflight.blocker))
        const uploadTail = computed(() => uploadJob.value && uploadJob.value.log.length ? uploadJob.value.log[uploadJob.value.log.length - 1] : '')
        const staleCodes = computed(() => upload.preflight ? upload.preflight.codes.filter(c => c.stale).map(c => c.code) : [])
        const uploadWarnings = computed(() => {
            const warnings = []
            for (const c of upload.preflight ? upload.preflight.codes : []) {
                for (const kind of Object.keys(WARNING_LABELS)) {
                    if (c[kind].length) warnings.push({code: c.code, kind, label: WARNING_LABELS[kind], names: c[kind]})
                }
            }
            return warnings
        })

        async function loadPreflight() {
            await guarded(async () => upload.preflight = await api('/api/upload/preflight'))
        }

        async function openUpload() {
            upload.open = true
            upload.armed = false
            upload.preflight = null
            await loadPreflight()
        }

        async function submitUpload(kind) {
            upload.armed = false
            try {
                await api('/api/jobs', 'POST', {kind})
            } catch (e) {
                error.value = e.message
                upload.open = false
            }
        }

        // the first click arms the button, the second one uploads
        function confirmUpload() {
            if (!upload.armed) {
                upload.armed = true
                setTimeout(() => upload.armed = false, 5000)
                return
            }
            return submitUpload('upload')
        }

        function isActive(job) {
            return job.status === 'queued' || job.status === 'running'
        }

        function stageText(f) {
            switch (f.stage) {
                case 'incoming': return 'incoming'
                case 'unsplit': return 'not split'
                case 'no_text': return `text ${f.n_text}/${f.n_segments}`
                case 'no_furigana': return `furi ${f.n_furigana}/${f.n_segments}`
                default: return `✓ ${f.n_segments}`
            }
        }

        function stepClass(n, total) {
            return !total || !n ? 'todo' : (n < total ? 'part' : 'ok')
        }

        async function guarded(fn) {
            try {
                error.value = ''
                return await fn()
            } catch (e) {
                error.value = e.message
            }
        }

        async function loadFiles() {
            await guarded(async () => {
                files.value = (await api(`/api/codes/${enc(code.value)}/files`)).files
            })
        }

        async function openFile(name) {
            await guarded(async () => {
                const details = await api(`/api/codes/${enc(code.value)}/files/${enc(name)}`)
                current.value = details
                activeIndex.value = -1
                cursorIndex.value = -1
                editIndex.value = -1
                historyOpen.value = false
                segmentEls.value = []
                location.hash = `${enc(details.code)}/${enc(details.name)}`
                await nextTick()
                createWave(details)
            })
        }

        function regionColor(i) {
            const s = current.value.segments[i]
            if (i === activeIndex.value) return cssVar('--region-active')
            if (!s.text) return cssVar('--region-empty')
            return cssVar(i % 2 ? '--region-b' : '--region-a')
        }

        function paintRegions() {
            if (!regions) return
            for (const region of regions.getRegions()) {
                if (!region.id.startsWith('preview')) region.setOptions({color: regionColor(Number(region.id))})
            }
        }

        function renderRegions() {
            if (!regions || waveLoading.value) return
            regions.clearRegions()
            const previewing = split.open && split.pieces
            current.value.segments.forEach((s, i) => {
                // a preview replaces the segments it is about to replace
                if (previewing && (split.index < 0 || split.index === i)) return
                regions.addRegion({
                    id: String(i),
                    start: s.start / 1000,
                    end: s.end / 1000,
                    content: String(i + 1),
                    color: regionColor(i),
                    drag: false,
                    resize: false,
                })
            })
            if (previewing) {
                split.pieces.forEach((piece, n) => regions.addRegion({
                    id: `preview-${n}`,
                    start: piece.start / 1000,
                    end: piece.end / 1000,
                    content: String(n + 1),
                    color: cssVar('--region-preview'),
                    drag: false,
                    resize: false,
                }))
            }
        }

        function createWave(details) {
            if (wave) wave.destroy()
            stopAt = null
            playing.value = false
            time.value = 0
            duration.value = details.length
            waveLoading.value = true

            regions = RegionsPlugin.create()
            wave = WaveSurfer.create({
                container: waveEl.value,
                url: `/audio/${enc(details.code)}/${enc(details.name)}`,
                height: 120,
                waveColor: cssVar('--wave'),
                progressColor: cssVar('--wave-progress'),
                cursorColor: cssVar('--accent'),
                cursorWidth: 2,
                normalize: true,
                minPxPerSec: zoom.value,
                audioRate: rate.value,
                plugins: [regions, TimelinePlugin.create()],
            })

            wave.on('decode', () => {
                waveLoading.value = false
                duration.value = wave.getDuration()
                renderRegions()
            })
            wave.on('error', e => {
                waveLoading.value = false
                error.value = `Audio: ${e.message || e}`
            })
            wave.on('play', () => playing.value = true)
            wave.on('pause', () => playing.value = false)
            wave.on('finish', () => playing.value = false)
            wave.on('timeupdate', t => {
                // the whole page re-renders on a time change, so only once a second
                if (Math.floor(t) !== lastSecond || !wave.isPlaying()) {
                    lastSecond = Math.floor(t)
                    time.value = t
                }
                trackCursor(t)
                if (stopAt !== null && t >= stopAt) {
                    stopAt = null
                    wave.pause()
                    return
                }
                if (stopAt === null) trackActive(t)
            })
            wave.on('interaction', () => stopAt = null)

            // a click moves the cursor (to cut there) and selects the segment, a double click plays it
            regions.on('region-clicked', region => {
                if (!region.id.startsWith('preview')) setActive(Number(region.id))
            })
            regions.on('region-double-clicked', (region, e) => {
                e.stopPropagation()
                if (region.id.startsWith('preview')) {
                    // listen to a piece of the preview
                    stopAt = region.end
                    wave.setTime(region.start)
                    wave.play()
                } else {
                    playSegment(Number(region.id))
                }
            })
        }

        function trackCursor(t) {
            const ms = t * 1000
            cursorIndex.value = current.value.segments.findIndex(s => ms > s.start && ms < s.end)
        }

        // follow the playback with the highlighted segment
        function trackActive(t) {
            const ms = t * 1000
            const i = current.value.segments.findIndex(s => ms >= s.start && ms < s.end)
            if (i >= 0 && i !== activeIndex.value) setActive(i)
        }

        function setActive(i) {
            activeIndex.value = i
            paintRegions()
            const el = segmentEls.value[i]
            if (el) el.scrollIntoView({block: 'nearest', behavior: 'smooth'})
        }

        function playSegment(i) {
            const s = current.value && current.value.segments[i]
            if (!s || !wave) return
            setActive(i)
            stopAt = stopAtEnd.value ? s.end / 1000 : null
            wave.setTime(s.start / 1000)
            wave.play()
        }

        function togglePlay() {
            if (!wave) return
            // from the cursor to the end of the segment it is in: handy to check where a cut would be
            const s = current.value.segments[cursorIndex.value]
            stopAt = !wave.isPlaying() && stopAtEnd.value && s ? s.end / 1000 : null
            wave.playPause()
        }

        // ---- editing: every action is saved by the server at once and returns the new state of the file ----

        function fileUrl() {
            return `/api/codes/${enc(current.value.code)}/files/${enc(current.value.name)}`
        }

        function applyDetails(details, active = activeIndex.value) {
            current.value = details
            editIndex.value = -1
            armedDelete.value = -1
            split.open = false
            split.pieces = null
            segmentEls.value = []
            activeIndex.value = Math.min(active, details.segments.length - 1)
            renderRegions()
            if (wave) trackCursor(wave.getCurrentTime())

            const {segments, ...status} = details
            const at = files.value.findIndex(f => f.name === details.name)
            if (at >= 0) files.value[at] = status
            if (historyOpen.value) loadBackups()
        }

        async function change(path, body, active, method = 'POST') {
            if (locked.value) return
            busy.value = true
            try {
                await guarded(async () => applyDetails(await api(fileUrl() + path, method, body), active))
            } finally {
                busy.value = false
            }
        }

        function segmentRef(i, extra = {}) {
            const s = current.value.segments[i]
            return {start: s.start, end: s.end, ...extra}
        }

        async function startEdit(i) {
            if (locked.value) return
            const s = current.value.segments[i]
            draft.text = s.text || ''
            draft.original_text = s.original_text === undefined ? null : s.original_text
            editIndex.value = i
            await nextTick()
            const input = Array.isArray(editInput.value) ? editInput.value[0] : editInput.value
            if (input) input.focus()
        }

        function saveText() {
            const i = editIndex.value
            const s = current.value.segments[i]
            const body = {}
            if (draft.text.trim() !== (s.text || '')) body.text = draft.text
            if (draft.original_text !== null && draft.original_text.trim() !== s.original_text) body.original_text = draft.original_text
            if (!Object.keys(body).length) {
                editIndex.value = -1
                return
            }
            return change(`/segments/${i}/text`, segmentRef(i, body), i, 'PUT')
        }

        const dropFurigana = i => change(`/segments/${i}/drop_furigana`, segmentRef(i), i)
        const revertCorrection = i => change(`/segments/${i}/revert_correction`, segmentRef(i), i)
        const joinNext = i => change(`/segments/${i}/join`, segmentRef(i), i)

        function cut(i, atCursor) {
            if (i < 0) return
            const extra = atCursor ? {at_ms: Math.round(wave.getCurrentTime() * 1000)} : {}
            return change(`/segments/${i}/split`, segmentRef(i, extra), i)
        }

        // the first click arms the button, the second one deletes
        function deleteSegment(i) {
            clearTimeout(armedTimer)
            if (armedDelete.value !== i) {
                armedDelete.value = i
                armedTimer = setTimeout(() => armedDelete.value = -1, 3000)
                return
            }
            return change(`/segments/${i}/delete`, segmentRef(i), i)
        }

        // ---- re-splitting with a preview on the wave ----

        function openSplit(i) {
            if (split.open && split.index === i) return closeSplit()
            Object.assign(split, splitDefaults.value, {open: true, index: i, pieces: null, note: ''})
            if (i >= 0) split.min_silence_len = Math.min(400, split.min_silence_len)  // it did not split with the default
            requestPreview()
        }

        function closeSplit() {
            split.open = false
            split.pieces = null
            renderRegions()
        }

        function splitBody(preview) {
            const params = {min_silence_len: split.min_silence_len, padding: split.padding, silence_thresh: split.silence_thresh, preview}
            return split.index < 0 ? params : segmentRef(split.index, params)
        }

        function splitPath() {
            return split.index < 0 ? '/split' : `/segments/${split.index}/resplit`
        }

        function requestPreview() {
            clearTimeout(previewTimer)
            previewTimer = setTimeout(() => guarded(async () => {
                const serial = ++previewSerial
                const result = await api(fileUrl() + splitPath(), 'POST', splitBody(true))
                if (serial !== previewSerial || !split.open) return
                split.pieces = result.pieces
                renderRegions()
            }), 150)
        }

        async function suggestPause() {
            await guarded(async () => {
                const result = await api(fileUrl() + '/suggest_pause')
                if (result.suggestion) {
                    split.min_silence_len = result.suggestion
                    split.note = `${result.pauses.length} pauses found, the border between short and long ones is about ${result.suggestion} ms`
                } else {
                    split.note = 'Too few pauses to guess'
                }
            })
        }

        async function applySplit(thenProcess) {
            const name = current.value.name
            await change(splitPath(), splitBody(false), Math.max(split.index, 0))
            if (thenProcess && !error.value) await submitJob('transcribe', name, {}, ['correct', 'furigana'])
        }

        watch(() => [split.min_silence_len, split.padding, split.silence_thresh], () => split.open && requestPreview())

        // ---- background jobs; their state comes through server-sent events ----

        async function submitJob(kind, name = current.value && current.value.name, params = {}, then = []) {
            await guarded(async () => {
                await api('/api/jobs', 'POST', {kind, code: code.value, name, params, then})
                jobsOpen.value = true
            })
        }

        const cancelJob = id => guarded(() => api(`/api/jobs/${id}/cancel`, 'POST'))

        async function reloadCurrent() {
            if (!current.value || editIndex.value >= 0) return
            await guarded(async () => {
                const details = await api(fileUrl())
                const playingNow = activeIndex.value
                applyDetails(details, playingNow)
            })
        }

        async function onJobEvent(job) {
            const at = jobs.value.findIndex(j => j.id === job.id)
            const previous = at >= 0 ? jobs.value[at] : null
            const merged = {...job, log: previous ? previous.log : []}
            if (previous) jobs.value[at] = merged
            else jobs.value.push(merged)
            if (job.status === 'running' && (!previous || previous.status !== 'running')) logJobId.value = job.id

            if (UPLOAD_KINDS.includes(job.kind)) {
                if (isActive(job)) return reloadCurrent()  // everything is locked while it runs
                // the dry run reindexes stale codes
                if (upload.open) await loadPreflight()
                await loadFiles()
                return reloadCurrent()
            }

            if (job.code !== code.value) return
            const aboutCurrent = current.value && (job.name === current.value.name || !job.name)
            const finished = !isActive(job)
            if (finished || !previous || previous.status !== job.status) await loadFiles()

            if (finished && job.result && current.value && job.name === current.value.name) {
                await openFile(job.result)  // converted: the file has a new name now
            } else if (aboutCurrent) {
                await reloadCurrent()  // texts show up while the transcription goes on
            }
        }

        function connectEvents() {
            const source = new EventSource('/api/events')
            source.onmessage = message => {
                const event = JSON.parse(message.data)
                if (event.type === 'jobs') {
                    jobs.value = event.jobs
                    fakeAi.value = event.fake_ai
                } else if (event.type === 'job') {
                    onJobEvent(event.job)
                } else if (event.type === 'log') {
                    const job = jobs.value.find(j => j.id === event.id)
                    if (job) {
                        job.log.push(event.line)
                        if (job.id === logJobId.value) nextTick(() => logEl.value && (logEl.value.scrollTop = logEl.value.scrollHeight))
                    }
                }
            }
        }

        async function loadBackups() {
            await guarded(async () => backups.value = (await api(fileUrl() + '/backups')).backups)
        }

        async function toggleHistory() {
            historyOpen.value = !historyOpen.value
            if (historyOpen.value) await loadBackups()
        }

        const restore = name => change(`/backups/${enc(name)}/restore`, undefined, activeIndex.value)

        async function undo() {
            await loadBackups()
            if (!backups.value.length) {
                error.value = 'Nothing to undo: no saved versions of this file'
                return
            }
            await restore(backups.value[0].name)
        }

        watch(code, async () => {
            files.value = []
            stageFilter.value = ''
            await loadFiles()
        })
        watch(zoom, z => wave && duration.value && wave.zoom(z))
        watch(rate, r => wave && wave.setPlaybackRate(r, true))

        window.addEventListener('keydown', e => {
            if (!current.value || ['INPUT', 'TEXTAREA', 'SELECT'].includes(e.target.tagName)) return
            if (e.metaKey || e.ctrlKey || e.altKey) return
            const actions = {
                ' ': togglePlay,
                'ArrowDown': () => playSegment(activeIndex.value + 1),
                'ArrowUp': () => playSegment(activeIndex.value - 1),
                'Enter': () => playSegment(activeIndex.value),
                'c': () => cut(cursorIndex.value, true),
                'e': () => activeIndex.value >= 0 && startEdit(activeIndex.value),
            }
            if (actions[e.key]) {
                e.preventDefault()
                actions[e.key]()
            }
        })

        window.addEventListener('click', e => {
            if (historyOpen.value && !e.target.closest('.history')) historyOpen.value = false
        })

        onMounted(() => guarded(async () => {
            const data = await api('/api/codes')
            codes.value = data.codes
            sourcePath.value = data.source_path
            splitDefaults.value = data.split_defaults
            connectEvents()

            const [hashCode, hashName] = location.hash.slice(1).split('/').map(decodeURIComponent)
            const known = data.codes.map(c => c.code)
            code.value = known.includes(hashCode) ? hashCode : (known.includes('JPLTX') ? 'JPLTX' : known[0] || '')
            if (code.value === hashCode && hashName) {
                await nextTick()
                await openFile(hashName)
            }
        }))

        return {
            codes, sourcePath, code, files, filter, stageFilter, current, error, stageChips, visibleFiles,
            waveEl, waveLoading, playing, time, duration, zoom, rate, stopAtEnd, activeIndex, segmentEls,
            busy, cursorIndex, editIndex, editInput, draft, armedDelete, historyOpen, backups,
            loadFiles, openFile, playSegment, togglePlay, stageText, stepClass, rubyHtml, fmtTime, fmtDate, plainOf,
            jobs, jobsOpen, logJobId, logEl, fakeAi, split, locked, plainCount, staleCount, codeBusy, canApplySplit,
            activeJobs, jobsNewestFirst, jobsSummary, logText,
            upload, uploadJob, uploadRunning, uploadDone, dryRun, canUpload, uploadTail, staleCodes, uploadWarnings,
            openUpload, submitUpload, confirmUpload,
            openSplit, closeSplit, suggestPause, applySplit, submitJob, cancelJob,
            uncorrectedCount, revertCorrection, diffHtml, plainText, wasChanged,
            startEdit, saveText, dropFurigana, joinNext, cut, deleteSegment, toggleHistory, restore, undo,
        }
    },
}).mount('#app')
