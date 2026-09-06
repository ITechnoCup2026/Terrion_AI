# Integrasi Fitur Perencanaan Tanam (AI) — Panduan Frontend

Panduan ini untuk mengintegrasikan fitur **rencana tanam semusim** ke
`Terrion_Frontend`. Fitur ini belum ada sama sekali di repo ini — tidak ada
`lib/planning/`, tidak ada halaman `/plans`. Jadi dokumen ini ditulis sebagai
panduan greenfield, bukan catatan perubahan.

> Salinan berkas ini juga ada di `Terrion_Frontend/docs/INTEGRASI_AI_PERENCANAAN.md`,
> tetapi folder `docs/` di repo itu masuk `.gitignore` — jadi versi yang
> ini yang tersimpan di git dan bisa dibagikan.

Ditulis terhadap `Terrion_Backend` branch `feat/rencana-tanam` (`6767124`) dan
`Terrion_AI` `main` (`25ade48`).

---

## 1. Hal pertama yang harus dipahami

**Frontend tidak pernah berbicara dengan layanan AI.** Tidak ada URL, tidak ada
token, tidak ada variabel lingkungan baru sama sekali di sisi ini.

```
Browser ──► Next.js (repo ini) ──► Terrion_Backend (Go) ──┬──► Postgres
                                                          └──► Terrion_AI (Python)
                                                               (opsional)
```

Yang FE panggil hanyalah `/api/plans*` di backend Go, persis seperti
`/api/plots` yang sudah ada. Kalau layanan AI mati, tidak ter-deploy, atau
lambat, **endpoint-nya tetap menjawab `200` dengan rencana yang lengkap dan
benar** — dihitung solver Go sendiri. Satu-satunya yang berubah adalah nilai
field `engine`.

Konsekuensinya untuk desain UI: **jangan pernah membuat layar yang gagal ketika
`engine` bernilai `"fallback"`.** Itu bukan kondisi error.

### Yang perlu disiapkan

Tidak ada. `NEXT_PUBLIC_API_URL` yang sudah dipakai `lib/api/client.ts` sudah
cukup. Semua konfigurasi AI (`AI_SERVICE_URL`, `AI_SERVICE_TOKEN`) hidup di
`.env` milik Go dan tidak pernah menyentuh browser.

---

## 2. Endpoint

Lima endpoint, semuanya di balik cookie sesi `terrion_session` yang sudah
ditangani `apiFetch`.

| Metode | Jalur | Peran | Guna |
| --- | --- | --- | --- |
| `GET` | `/api/plans/propose?season=<label>&goal=<kalimat>` | **pengurus** | hitung tiga usulan rencana; tidak menyimpan apa pun |
| `POST` | `/api/plans` | **pengurus** | simpan satu rencana yang dipilih |
| `GET` | `/api/plans` | semua peran | daftar rencana tersimpan |
| `GET` | `/api/plans/:id` | semua peran | satu rencana tersimpan beserta itemnya |
| `POST` | `/api/plans/:id/cancel` | **pengurus** | batalkan rencana dan lepas blok-bloknya |

Perhatikan tiga hal yang mudah salah:

- `propose` memakai **`GET`**, bukan `POST`, dan parameternya lewat **query
  string** `?season=`, bukan body.
- `goal` **opsional**: kalimat tujuan pengurus dalam bahasa Indonesia, maksimal
  500 aksara. Kosongkan kalau pengurus tidak menyatakan apa-apa — tujuan kosong
  berarti bobot bawaan dan **nol panggilan model**, jadi jawabannya lebih cepat.
  Lihat §3.4.
- Pembatalan memakai **`POST /api/plans/:id/cancel`**, bukan
  `DELETE /api/plans/:id`.
- `propose` dan `POST /api/plans` memerlukan peran **pengurus**. Peran lain
  dapat `403`. Daftar dan detail boleh dibaca peran mana pun yang terhubung ke
  koperasi.

Semua respons memakai amplop yang sama seperti endpoint lain:

```jsonc
{ "data": { /* ... */ } }          // sukses
{ "errors": "kode_atau_pesan" }    // gagal
```

`apiFetch` sudah membuka amplop itu dan melempar `ApiError` pada kegagalan,
jadi tipe generiknya diisi bentuk `data`-nya saja.

---

## 3. Bentuk data

Salin apa adanya ke `lib/planning/types.ts`. Nama field di bawah persis sama
dengan yang dikirim Go.

### 3.1 Respons `propose`

```ts
export type ProposalResponse = {
  season: SeasonResponse
  /** Selalu "climatology" untuk sekarang: jendela panen dari normal iklim. */
  basis: string
  /** "ai-service" kalau layanan AI menjawab, "fallback" kalau solver Go. */
  engine: 'ai-service' | 'fallback'
  /** Berapa panen tercatat yang mengkalibrasi model hasil. 0 = murni model. */
  yield_observations: number
  /** Satu kalimat batas yang WAJIB tampil di layar, apa adanya. */
  limits: string
  /** Pembanding musim lalu. null = belum ada musim pembanding, BUKAN nol ton. */
  previous_season: PreviousSeasonResponse | null
  /** Selalu tiga, satu per objektif, urut aman lalu pendapatan lalu pasar. */
  plans: CandidatePlanResponse[]
  /** Lahan yang tidak bisa dimasukkan rencana. Wajib ditampilkan. */
  skipped: SkippedPlotResponse[]
  /** Jumlah kombinasi yang dievaluasi. Diagnostik, bukan untuk pengguna. */
  evaluations: number
}

export type SeasonResponse = {
  label: string          // "MT I 2026/2027"
  start: string          // "2026-10-01"
  end: string            // "2027-03-31"
  planting_from: string  // batas tanam paling awal
  planting_to: string    // batas tanam paling akhir
}

export type PreviousSeasonResponse = {
  label: string          // "MT I 2025/2026"
  peak_tonnes: number
  total_tonnes: number
  blocks: number
}

export type CandidatePlanResponse = {
  objective: 'aman' | 'pendapatan' | 'pasar'
  /** Paragraf bahasa Indonesia. Bisa kosong; perlakukan sebagai opsional. */
  narrative: string
  metrics: PlanMetricsResponse
  assignments: PlanAssignmentResponse[]
  /** Ambang tiap komoditas, ditandai atau tidak. Jawaban atas "dibanding apa?". */
  thresholds: CommodityThresholdResponse[]
  /** Minggu yang melewati ambang, satu baris per minggu. Kosong = tidak ada. */
  flagged: PlanFlaggedWeekResponse[]
  /** Kebutuhan pupuk rencana ini — dasar RDKK sebelum benih masuk tanah. */
  fertiliser: FertiliserLineResponse[]
  /** Komoditas yang belum punya tarif. Tampilkan "—", JANGAN tampilkan 0 kg. */
  fertiliser_unrated: string[]
  /** Anggota yang garapannya melewati batas subsidi 2 ha. Ditandai, tidak dipotong. */
  over_subsidy_cap: OverSubsidyCapResponse[]
}

export type CommodityThresholdResponse = {
  commodity_id: string
  tonnes_per_week: number
  /** Dari mana ambangnya: kapasitas tampung koperasi atau bawaan. */
  basis: string
}

export type PlanFlaggedWeekResponse = {
  iso_week: string        // "2027-W03"
  commodity_id: string
  tonnes: number
  threshold_tonnes: number
  basis: string
}

export type FertiliserLineResponse = {
  input_item: string      // "Urea"
  quantity_kg: number
  /** Komoditas yang menyumbang angka ini. */
  sources: string[]
}

export type OverSubsidyCapResponse = {
  member_id: string
  member_name: string
  planted_ha: number
  excess_ha: number
}

export type PlanMetricsResponse = {
  /** Puncak panen mingguan pada musim rata-rata, ton. */
  peak_tonnes_expected: number
  /** Puncak panen mingguan pada musim terburuk, ton. */
  peak_tonnes_worst: number
  /** Nilai kotor perkiraan. NULL kalau tidak ada harga acuan. */
  gross_value: number | null
  /** Permintaan pembeli yang tertutup rencana ini, kg. */
  demand_covered_kg: number
  /** Total panen semusim pada perkiraan tengah, ton. */
  total_tonnes_mid: number
  /** Berapa minggu yang melewati kapasitas tampung. 0 = aman. */
  flagged_weeks: number
}

export type PlanAssignmentResponse = {
  plot_id: string
  plot_name: string
  member_id: string
  member_name: string
  area_ha: number
  commodity_id: string
  variety_id: string
  variety_name: string
  planting_date: string   // "2026-10-05"
  harvest_start: string
  harvest_end: string
  plausibility: 'ok' | 'early' | 'late' | 'implausible'
  tonnes_low: number
  tonnes_mid: number
  tonnes_high: number
}

export type SkippedPlotResponse = {
  plot_id: string
  plot_name: string
  member_name: string
  /** Kalimat siap tampil, sudah berbahasa Indonesia. */
  reason: string
}
```

### 3.2 Permintaan `POST /api/plans`

```ts
export type ApplySeasonPlanRequest = {
  /** Harus sama dengan season.label dari propose. Minimal 3 karakter. */
  season_label: string
  objective: 'aman' | 'pendapatan' | 'pasar'
  /** Minimal satu. Biasanya seluruh assignments dari rencana yang dipilih. */
  assignments: {
    plot_id: string
    variety_id: string
    planting_date: string  // "2006-01-02", divalidasi ketat
  }[]
}

export type ApplySeasonPlanResponse = {
  plan_id: string
  /** Berapa blok tanam yang dibuat. */
  blocks: number
}
```

Balasannya **`201 Created`**, bukan `200`.

### 3.3 Rencana tersimpan

```ts
export type SeasonPlanResponse = {
  id: string
  season_label: string
  season_start: string
  season_end: string
  objective: 'aman' | 'pendapatan' | 'pasar'
  status: 'applied' | 'cancelled'
  created_at: string          // RFC3339 UTC
  cancelled_at: string | null
  /** Kosong pada GET /api/plans; terisi pada GET /api/plans/:id. */
  items: SeasonPlanItemResponse[]
}

export type SeasonPlanItemResponse = {
  id: string
  plot_id: string
  plot_name: string
  member_id: string
  member_name: string
  commodity_id: string
  commodity_name: string
  variety_id: string
  variety_name: string
  area_ha: number
  planting_date: string
  harvest_start: string
  harvest_end: string
  plausibility: string
  tonnes_low: number
  tonnes_mid: number
  tonnes_high: number
  block_id: string | null
}

export type SeasonPlanListResponse = { plans: SeasonPlanResponse[] }
export type CancelSeasonPlanResponse = { plan_id: string; blocks_removed: number }
```

**Penting:** `GET /api/plans` mengembalikan `items: []` untuk setiap rencana —
daftar tidak memuat isinya. Untuk menampilkan detail, panggil
`GET /api/plans/:id`. Jangan membangun layar daftar yang bergantung pada
`items`.

### 3.4 Tujuan pengurus (`goal`)

`propose` menerima satu parameter opsional berisi kalimat tujuan pengurus:

```
/api/plans/propose?season=MT%20I%202026%2F2027&goal=musim%20depan%20jangan%20menumpuk
```

Yang perlu diketahui FE, dan tidak lebih dari ini:

- **Maksimal 500 aksara** (aksara, bukan byte). Lebih dari itu ditolak
  `422 plan_goal_too_long`. Batasi di kolom isian, jangan biarkan pengurus
  menulis panjang lalu kehilangan rencananya.
- **Kosong itu wajar dan lebih cepat.** Tanpa tujuan, backend memakai bobot
  bawaan dan tidak memanggil model sama sekali. Jangan mengirim string kosong
  sebagai "netral" — cukup jangan sertakan parameternya.
- **Tujuan menggeser penekanan, bukan mengganti arti.** Rencana "Aman" tetap
  rencana yang meratakan puncak panen; tujuan hanya menggeser seberapa kuat
  penekanannya. Kalau kalimatnya meminta sesuatu yang membalik arti label,
  permintaan itu diabaikan dan alasannya dicatat di sisi layanan.
- **Tujuan tidak pernah menjadi angka.** Seluruh tonase, rupiah, dan tanggal
  tetap dihitung solver deterministik. Tidak ada angka di layar yang berasal
  dari model bahasa.
- **Tujuan yang berbeda berarti perhitungan yang berbeda**, jadi ia ikut
  menjadi kunci cache. Mengubah kalimatnya berarti menunggu penuh lagi.

Bentuk isiannya bebas: daftar pilihan siap pakai ("jangan menumpuk di satu
minggu", "utamakan permintaan pembeli", "kejar pendapatan tertinggi") lebih
mudah dipakai pengurus daripada kotak teks kosong, dan keduanya dikirim lewat
parameter yang sama.

---

## 4. Kode error

`ApiError.code` berisi salah satu kode di bawah. Semuanya sudah stabil dan
boleh dipetakan langsung ke kalimat Indonesia di UI.

| HTTP | `code` | Artinya | Saran tampilan |
| --- | --- | --- | --- |
| 401 | `Unauthorised` | tidak ada sesi | arahkan ke login |
| 403 | `Forbidden` | peran bukan pengurus | sembunyikan tombolnya sejak awal |
| 403 | `account is not linked to a cooperative` | akun belum punya koperasi | ajak melengkapi profil |
| 400 | `season is required` | query `season` kosong | bug FE, jangan tampilkan mentah |
| 422 | `plan_goal_too_long` | `goal` lebih dari 500 aksara | minta perpendek; jangan buang isian pengurus |
| 422 | `plan_no_plots` | koperasi belum punya lahan | ajak menambah lahan |
| 422 | `plan_no_climate_normals` | tidak ada normal iklim untuk sel lahan | jelaskan data cuaca belum siap |
| 422 | `plan_season_closed` | jendela tanam musim itu sudah lewat | tawarkan musim berikutnya |
| 422 | `plan_no_eligible_plots` | ada lahan, tapi tidak satu pun layak | tampilkan `skipped` kalau ada |
| 422 | `plan_already_applied` | musim itu sudah punya rencana aktif | tawarkan lihat atau batalkan yang ada |
| 422 | `plan_already_cancelled` | rencana sudah dibatalkan | segarkan daftar |
| 422 | `plan_assignment_rejected` | satu assignment ditolak validasi | minta ulangi propose |
| 422 | `plan_partially_cancellable` | sebagian blok sudah dipanen | jelaskan tidak bisa dibatalkan penuh |
| 404 | `plan_not_found` | id salah atau milik koperasi lain | halaman tidak ditemukan |
| 500 | `request failed` | galat tak terduga | pesan umum, jangan bocorkan |
| 0 | (`NETWORK_ERROR`) | backend tidak tercapai | bedakan dari 404, lihat `lib/api/client.ts` |

---

## 5. Contoh implementasi

Mengikuti pola `lib/plots/load.ts` yang sudah ada: modul server-only, menerima
`sessionId`, memakai `apiFetch`.

### `lib/planning/load.ts`

```ts
import { apiFetch, isNotFound } from '@/lib/api/client'

import type {
  ProposalResponse,
  SeasonPlanListResponse,
  SeasonPlanResponse,
} from './types'

/**
 * Tiga usulan rencana untuk satu musim. Tidak menyimpan apa pun.
 *
 * Panggilan ini bisa memakan 2-4 detik: backend menghitung ratusan kombinasi
 * dan, kalau layanan AI hidup, menunggu narasinya. Selalu render loading state
 * yang jujur, jangan optimistic UI.
 */
export async function loadProposal(
  sessionId: string,
  season: string,
  goal?: string,
): Promise<ProposalResponse> {
  // Tujuan kosong sengaja tidak dikirim: tanpa parameter ini backend memakai
  // bobot bawaan dan melewati panggilan model, jadi jawabannya lebih cepat.
  const trimmed = goal?.trim()

  return apiFetch<ProposalResponse>('/api/plans/propose', {
    sessionId,
    query: trimmed ? { season, goal: trimmed } : { season },
  })
}

export async function loadPlans(sessionId: string): Promise<SeasonPlanResponse[]> {
  const { plans } = await apiFetch<SeasonPlanListResponse>('/api/plans', { sessionId })
  return plans
}

export async function loadPlan(
  sessionId: string,
  id: string,
): Promise<SeasonPlanResponse | null> {
  try {
    return await apiFetch<SeasonPlanResponse>(`/api/plans/${id}`, { sessionId })
  } catch (error) {
    if (isNotFound(error)) return null
    throw error
  }
}
```

### `lib/planning/actions.ts`

```ts
'use server'

import { apiFetch } from '@/lib/api/client'
import { currentSessionId } from '@/lib/auth/session'

import type {
  ApplySeasonPlanRequest,
  ApplySeasonPlanResponse,
  CancelSeasonPlanResponse,
} from './types'

export async function applyPlan(
  request: ApplySeasonPlanRequest,
): Promise<ApplySeasonPlanResponse> {
  const sessionId = await currentSessionId()
  return apiFetch<ApplySeasonPlanResponse>('/api/plans', {
    method: 'POST',
    body: request,
    sessionId,
  })
}

export async function cancelPlan(id: string): Promise<CancelSeasonPlanResponse> {
  const sessionId = await currentSessionId()
  return apiFetch<CancelSeasonPlanResponse>(`/api/plans/${id}/cancel`, {
    method: 'POST',
    sessionId,
  })
}
```

### Menyusun permintaan `apply` dari rencana terpilih

```ts
export function toApplyRequest(
  season: SeasonResponse,
  plan: CandidatePlanResponse,
): ApplySeasonPlanRequest {
  return {
    season_label: season.label,
    objective: plan.objective,
    assignments: plan.assignments.map((a) => ({
      plot_id: a.plot_id,
      variety_id: a.variety_id,
      planting_date: a.planting_date,
    })),
  }
}
```

Tiga field itu saja yang dikirim balik. Semua angka lain dihitung ulang backend
dari awal — mengirimnya tidak berguna dan tidak akan dipercaya.

---

## 6. Alur layar yang disarankan

```
/plans                    daftar rencana tersimpan (semua peran)
/plans/[id]               detail satu rencana + tombol batalkan (pengurus)
/plans/propose?season=…   tiga usulan berdampingan + tombol pilih (pengurus)
```

Alur `propose`:

1. Pengurus memilih musim dan, kalau mau, menyatakan tujuannya — dari daftar
   pilihan siap pakai atau diketik bebas — lalu panggil `loadProposal`.
   Tujuannya opsional; tanpa itu rencananya tetap terbit, hanya lebih kaku.
2. Tampilkan `limits` apa adanya di dekat ketiga kartu, dan `previous_season`
   sebagai pembanding. `previous_season: null` berarti belum ada musim
   pembanding — tulis "—", **bukan 0 ton**.
3. Tampilkan **tiga kartu berdampingan**, satu per objektif. Ketiganya sah;
   tidak ada yang "paling benar". Bedanya pertanyaan yang dijawab:
   - **aman** — "kalau cuaca membuat panen menumpuk, apa gudang masih muat?"
   - **pendapatan** — "mana yang paling bernilai?"
   - **pasar** — "mana yang memenuhi kontrak pembeli yang sudah ada?"
4. Setiap kartu menampilkan `narrative`, lalu metrik, lalu `thresholds` dan
   `flagged` (puncak dibandingkan terhadap apa, dan minggu mana yang lewat),
   lalu `fertiliser` beserta `over_subsidy_cap`, lalu tabel `assignments`.
   Komoditas di `fertiliser_unrated` ditulis "—", **bukan 0 kg**: "belum ada
   angkanya" dan "butuh nol kilogram" dua hal yang berbeda.
5. Tampilkan `skipped` di bawah ketiga kartu. **Jangan disembunyikan** — kalau
   lahan seorang anggota hilang tanpa penjelasan, pengurus akan menganggap
   sistemnya rusak.
6. Pilih satu, panggil `applyPlan`, lalu arahkan ke `/plans/[plan_id]`.

---

## 7. Sepuluh hal yang mudah salah

**1. `engine: "fallback"` bukan error.** Rencananya lengkap, angkanya benar,
dihitung solver Go. Kalau ingin menampilkannya, cukup badge kecil yang netral.
Jangan toast merah, jangan blokir tombol simpan.

**2. `narrative` boleh kosong.** Perlakukan sebagai opsional dan sediakan tata
letak yang tetap rapi tanpanya. Backend tidak memberi tahu apakah teks itu
ditulis model bahasa atau templat — dan memang tidak perlu diberitahukan ke
pengguna.

**3. `peak_tonnes_expected` dan `peak_tonnes_worst` bukan persentil.** Namanya
"perkiraan tengah" dan "kasus terburuk". **Jangan** menulis "P50", "P90", atau
"90% kemungkinan" di UI — angka itu tidak berasal dari distribusi yang
dilaporkan ke frontend. Kalimat yang aman: *"pada musim rata-rata"* dan *"pada
musim terburuk"*.

**4. `gross_value` bisa `null`,** dan ketika ada pun **panel harga acuannya
masih sintetis.** Jangan tampilkan sebagai rupiah pasti. Beri kata "perkiraan"
dan hindari membandingkan dua rencana semata-mata lewat angka ini.

**5. `propose` lambat.** 2-4 detik wajar, dan itu memang batas anggarannya.
Butuh skeleton atau spinner sungguhan. Jangan pasang timeout FE di bawah 6
detik.

**6. `propose` tidak menyimpan apa pun.** Menyegarkan halaman berarti menghitung
ulang. Kalau ingin pengguna bisa membandingkan lalu kembali, simpan hasilnya di
state, bukan mengandalkan panggilan ulang.

**7. `GET /api/plans` mengembalikan `items: []`.** Detail hanya ada di
`GET /api/plans/:id`.

**8. `plausibility` ada empat nilai,** dan `implausible` berarti jendela
panennya meragukan. Bedakan secara visual — minimal `early` dan `late` diberi
penanda, `implausible` diberi peringatan.

**9. Peran menentukan tombol.** `propose`, `apply`, dan `cancel` hanya untuk
pengurus. Sembunyikan tombolnya berdasarkan peran, jangan menunggu `403`.

**10. Pembatalan bisa ditolak sebagian.** `plan_partially_cancellable` muncul
kalau sebagian blok sudah dipanen. Siapkan kalimatnya, jangan tampilkan kode
mentah.

---

## 8. Yang tidak ada di API ini

Supaya tidak dicari-cari:

- **`narrative_source`** (`"llm"` atau `"template"`) — ada di dalam layanan AI,
  tidak diteruskan ke FE.
- **`degraded`** — daftar alasan narasi gagal. Diagnostik internal.
- **`peak_tonnes_p50` dan `p90`** — layanan AI menghitungnya, tetapi Go **tidak
  memakainya sama sekali** dan tidak meneruskannya. Metrik yang sampai ke FE
  seluruhnya dihitung ulang Go dari tabel kandidatnya sendiri.

Kalau salah satunya benar-benar dibutuhkan UI, itu perubahan di sisi Go
(`internal/model/planning.go` dan `internal/model/converter/planning_converter.go`),
bukan sesuatu yang bisa diakali dari FE.

---

## 9. Menguji secara lokal

Tiga proses, urut:

```bash
# 1. layanan AI (opsional — lewati untuk menguji jalur fallback)
cd Terrion_AI
uvicorn app.main:app --port 8080

# 2. backend Go
cd Terrion_Backend
go run ./cmd/web            # :8000

# 3. frontend
cd Terrion_Frontend
pnpm dev                    # NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
```

**Uji kedua jalurnya.** Matikan proses nomor 1, muat ulang layar propose, dan
pastikan layarnya tetap utuh dengan `engine: "fallback"`. Kalau layarnya rusak,
itu bug FE — bukan bug layanan AI.

Untuk melihat jalur AI benar-benar terpakai, pastikan `AI_SERVICE_URL` terisi di
`Terrion_Backend/.env` dan periksa `engine` bernilai `"ai-service"`.

---

## 10. Checklist

- [ ] `lib/planning/types.ts` — tipe dari bagian 3
- [ ] `lib/planning/load.ts` — `loadProposal`, `loadPlans`, `loadPlan`
- [ ] `lib/planning/actions.ts` — `applyPlan`, `cancelPlan`
- [ ] Pemetaan kode error dari bagian 4 ke kalimat Indonesia
- [ ] `/plans` daftar, `/plans/[id]` detail, `/plans/propose` usulan
- [ ] Tombol pengurus disembunyikan untuk peran lain
- [ ] Loading state yang menahan 2-4 detik
- [ ] `skipped` ditampilkan
- [ ] `narrative` kosong tetap rapi
- [ ] `gross_value` null tetap rapi
- [ ] Diuji dengan layanan AI mati (`engine: "fallback"`)
- [ ] Tidak ada tulisan "P50", "P90", atau klaim probabilitas di UI
