import {createApp, ref, computed, watch, onMounted, nextTick} from 'https://cdn.jsdelivr.net/npm/vue@3.5.43/dist/vue.esm-browser.prod.js'
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

async function api(path) {
    const response = await fetch(path)
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

        // wavesurfer objects are kept out of Vue reactivity
        let wave = null
        let regions = null
        let stopAt = null

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
                regions.clearRegions()
                details.segments.forEach((s, i) => regions.addRegion({
                    id: String(i),
                    start: s.start / 1000,
                    end: s.end / 1000,
                    content: String(i + 1),
                    color: regionColor(i),
                    drag: false,
                    resize: false,
                }))
            })
            wave.on('error', e => {
                waveLoading.value = false
                error.value = `Audio: ${e.message || e}`
            })
            wave.on('play', () => playing.value = true)
            wave.on('pause', () => playing.value = false)
            wave.on('finish', () => playing.value = false)
            wave.on('timeupdate', t => {
                time.value = t
                if (stopAt !== null && t >= stopAt) {
                    stopAt = null
                    wave.pause()
                    return
                }
                if (stopAt === null) trackActive(t)
            })
            wave.on('interaction', () => stopAt = null)

            regions.on('region-clicked', (region, e) => {
                e.stopPropagation()
                playSegment(Number(region.id))
            })
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
            stopAt = null
            wave.playPause()
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
            const actions = {
                ' ': togglePlay,
                'ArrowDown': () => playSegment(activeIndex.value + 1),
                'ArrowUp': () => playSegment(activeIndex.value - 1),
                'Enter': () => playSegment(activeIndex.value),
            }
            if (actions[e.key]) {
                e.preventDefault()
                actions[e.key]()
            }
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
            loadFiles, openFile, playSegment, togglePlay, stageText, stepClass, rubyHtml, fmtTime,
        }
    },
}).mount('#app')
