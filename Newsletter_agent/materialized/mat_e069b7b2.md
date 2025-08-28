# Alibaba AI Team Just Released Ovis 2.5 Multimodal LLMs: A Major Leap in Open-Source AI with Enhanced Visual Perception and Reasoning Capabilities

> Source: https://www.marktechpost.com/2025/08/17/alibaba-ai-team-just-released-ovis-2-5-multimodal-llms-a-major-leap-in-open-source-ai-with-enhanced-visual-perception-and-reasoning-capabilities/

Ovis2.5, the latest large multimodal language model (MLLM) from Alibaba’s AIDC-AI team, is making waves in the open-source AI community with its 9B and 2B parameter variants. Ovis2.5 sets new benchmarks for performance and efficiency by introducing technical advances geared toward native-resolution vision perception, deep multimodal reasoning, and robust OCR — tackling long-standing limitations faced by most MLLMs in processing high-detail visual information and complex reasoning.

Native-Resolution Vision and Deep Reasoning

A defining innovation in Ovis2.5 is its integration of a native-resolution vision transformer (NaViT), which processes images at their original, variable resolutions. Unlike previous models that relied on tiling or forced resizing, often resulting in a loss of important global context and fine detail, NaViT preserves the full integrity of both intricate charts and natural images. This upgrade allows the model to excel at visually dense tasks ranging from scientific diagrams to complex infographics and forms.

To address challenges in reasoning, Ovis2.5 implements a curriculum that goes beyond standard chain-of-thought (CoT) supervision. Its training data includes “thinking-style” samples for self-correction and reflection, culminating in an optional “thinking mode” at inference time. Users can enable this mode (as discussed enthusiastically in the LocalLLaMA Reddit thread) to trade faster response times for enhanced step-by-step accuracy and model introspection. This is particularly beneficial on tasks requiring deeper multimodal analysis, such as scientific question answering or mathematical problem solving.

Performance Benchmarks and State-of-the-Art Results

Ovis2.5-9B achieves an average score of 78.3 on the OpenCompass multimodal leaderboard, putting it ahead of all open-source MLLMs under 40B parameters; Ovis2.5-2B scores 73.9, setting a new standard for lightweight models ideal for on-device or resource-constrained inference. Both models deliver exceptional results on specialized domains, leading open-source competitors in:

STEM reasoning (MathVista, MMMU, WeMath)

OCR and chart analysis (OCRBench v2, ChartQA Pro)

Visual grounding (RefCOCO, RefCOCOg)

Video and multi-image comprehension (BLINK, VideoMME)Ovis2_5_Tech_Report.pdfx

Technical commentary on Reddit and X highlight the remarkable advances in OCR and document processing, with users noting improved extraction of text in cluttered images, robust form understanding, and flexible support for complex visual queries.

High-Efficiency Training and Scalable Deployment

Ovis2.5 optimizes end-to-end training efficiency by employing multimodal data packing and advanced hybrid parallelism, delivering up to a 3–4× speedup in overall throughput. Its lightweight 2B variant continues the series’ “small model, big performance” philosophy, enabling high-quality multimodal understanding on mobile hardware and edge devices.

Summary

Alibaba’s newly released Ovis2.5 models (9B and 2B) mark a breakthrough in open-source multimodal AI, boasting state-of-the-art scores on the OpenCompass leaderboard for models under 40B parameters. Key innovations include a native-resolution vision transformer that adeptly processes high-detail visuals without tiling, and an optional “thinking mode” that enables deeper self-reflective reasoning on complex tasks. Ovis2.5 excels in STEM, OCR, chart analysis, and video understanding, outperforming previous open models and narrowing the gap to proprietary AI. Its efficiency-focused training and lightweight 2B variant make advanced multimodal capabilities accessible for both researchers and resource-constrained applications.