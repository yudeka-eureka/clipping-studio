# Product-First Landing Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Selaraskan landing page dengan workflow Clipping Studio memakai copy yang faktual, visual product-first, dan CTA yang jelas.

**Architecture:** Pertahankan komponen `LandingPage` dan stylesheet landing yang sudah ada. Perubahan difokuskan pada hierarchy hero, label mockup, feature/workflow copy, dan metadata route; tidak ada perubahan pada backend, routing generated, atau autentikasi.

**Tech Stack:** React, TanStack Router, TypeScript, CSS, Vitest.

**Spec:** `backend/docs/superpowers/specs/2026-11-19-product-first-landing-design.md`

## Global Constraints

- Copy harus menjelaskan upload/link video → opsi klip → proses → tinjau/unduh.
- Jangan memakai klaim viralitas, hasil pasti, testimoni, angka performa, atau foto stok generik.
- CTA harus tetap mengarah ke alur autentikasi/workspace yang sudah ada.
- Jangan mengedit `frontend/src/routeTree.gen.ts` karena file generated.

## Review Focus

- Hero pada layar sempit tidak boleh overflow horizontal — verifikasi production build dan inspeksi CSS responsive.
- Semua CTA anonymous dan authenticated tetap memakai handler yang sama — verifikasi existing app routing tests.
- Copy tidak menyebut fitur yang tidak ada — grep hasil akhir untuk klaim terlarang dan review terhadap spec.

### Task 1: Rewrite landing content

**Files:**
- Modify: `frontend/src/components/pages/LandingPage.tsx`
- Test: existing `frontend/src/test/app-routing.test.tsx`

- [ ] Update hero headline, lede, badges, and CTA copy to factual Indonesian language.
- [ ] Replace decorative labels that imply guaranteed or finished posting with labels describing review/render workflow.
- [ ] Align feature, workflow, and product-preview copy with actual app capabilities while keeping existing anchor IDs and handlers.
- [ ] Run focused route test.

### Task 2: Align visual treatment and metadata

**Files:**
- Modify: `frontend/src/styles/landing.css`
- Modify: `frontend/src/routes/index.tsx`

- [ ] Tune hero/product-preview surfaces, contrast, and responsive layout to the existing Material 3 lilac workspace tokens.
- [ ] Keep the UI mockup as the visual proof; add no external photo dependency.
- [ ] Update page title and description to match the factual copy.
- [ ] Run frontend lint and build.

### Task 3: Whole-branch verification

- [ ] Run `npm test -- --run` from `frontend`.
- [ ] Run `npm run lint` from `frontend`.
- [ ] Run `npm run build` from `frontend`.
- [ ] Review diff and confirm only intended landing files plus approved docs/branch metadata changed.
