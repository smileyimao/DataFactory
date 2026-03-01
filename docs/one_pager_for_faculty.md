# Data Pipeline for Perception Research — One-Page Summary

**Contact:** Yimao He | Graduate Student, Engineering | Graduating April 2026

---

## The Problem

Research projects that collect video, images, LiDAR, or other sensor data often face:

- **Duplicate files** wasting storage and skewing analysis
- **Corrupt or low-quality data** (blurry, too dark, decoding failures) mixed with good data
- **Unstructured storage** making it hard to find "clean" subsets for training or analysis
- **No audit trail** — hard to trace which data was used for which model or paper

---

## The Solution: An Automated Data Pipeline

I have built a config-driven pipeline that:

1. **Ingests** raw data and pre-filters: deduplication (MD5 fingerprint), decode checks (failed files quarantined)
2. **Quality control** — rule-based (brightness, blur, contrast) + optional AI screening (YOLO)
3. **Human review** — borderline cases go to a web dashboard for approve/reject
4. **Structured archive** — passed data organized by batch, with reports, manifests, and version mapping

**Features:** Retry logic, health checks, path decoupling, MLflow integration. Extensible to LiDAR, audio, vibration. Designed for edge deployment and MLOps workflows.

---

## What I Can Offer

| For you | For me |
|---------|--------|
| **Free** data cleaning, deduplication, quality grading, and structured organization of your video/image/sensor datasets | Validation on **real research data** — helps me improve the pipeline and document it for my thesis |

**Ideal fit:** Faculty with datasets (video, images, LiDAR, or other sensors) that need cleaning, deduplication, quality grading, or structured organization, and who are open to a student working with their data until April 2026.

---

## Next Step

If you have data needs or know a colleague who might benefit, please reach out. I can provide a short demo, technical documentation, or run a pilot on a small subset of your data.

**Contact:** [Your email]

---

*One-page summary — feel free to forward to colleagues.*
