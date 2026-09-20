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

        // wavesurfer objects are kept out of Vue reactivity
        let wave = null
        let regions = null
        let stopAt = null
        let lastSecond = -1
        let armedTimer = null

        const stageChips = computed(() => STAGES.map(s => ({
            ...s, count: files.value.filter(f => f.stage === s.stage).length,
        })).filter(s => s.count))

        const visibleFiles = computed(() => {
            const needle = filter.value.trim().toLowerCase()
            return files.value.filter(f =>
                (!stageFilter.value || f.stage === stageFilter.value) &&
                (!needle || f.name.toLowerCase().includes(needle) || f.title.toLowerCase().includes(needle)))
        })

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
                region.setOptions({color: regionColor(Number(region.id))})
            }
        }

        function renderRegions() {
            if (!regions || waveLoading.value) return
            regions.clearRegions()
            current.value.segments.forEach((s, i) => regions.addRegion({
                id: String(i),
                start: s.start / 1000,
                end: s.end / 1000,
                content: String(i + 1),
                color: regionColor(i),
                drag: false,
                resize: false,
            }))
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
            regions.on('region-clicked', region => setActive(Number(region.id)))
            regions.on('region-double-clicked', (region, e) => {
                e.stopPropagation()
                playSegment(Number(region.id))
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
            if (busy.value) return
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
            startEdit, saveText, dropFurigana, joinNext, cut, deleteSegment, toggleHistory, restore, undo,
        }
    },
}).mount('#app')
