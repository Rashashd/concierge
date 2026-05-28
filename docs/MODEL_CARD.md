# Concierge Intent Classifier Model Card

## Task

Visitor intent classification for the Concierge router.

The model predicts one of four labels:

- `spam` — drop before storage or agent use
- `question` — route to the RAG workflow
- `lead` — route to lead capture workflow
- `escalate` — route to human handoff or escalation workflow

## Product use

The classifier is used as a cheap router before the expensive tool-calling agent path. Low-confidence predictions should be handed to the agent instead of forcing a deterministic workflow.

## Dataset

Public labeled text-classification sources:

- SMS Spam Collection for `spam`
- CLINC150 / `clinc_oos` public intent dataset for `question`, `lead`, and `escalate`

The CLINC150 intent labels are collapsed into Concierge router labels using a transparent mapping in the notebook.

Dataset SHA-256: `894e9a9c6ac512789458f5385839347eb68ace52fc2b6158e89ceb53d54cf350`

Balanced examples per class: `264`

Source counts:

[
  {
    "label": "escalate",
    "source_dataset": "DeepPavlov/clinc_oos",
    "count": 264
  },
  {
    "label": "lead",
    "source_dataset": "DeepPavlov/clinc_oos",
    "count": 264
  },
  {
    "label": "question",
    "source_dataset": "DeepPavlov/clinc_oos",
    "count": 264
  },
  {
    "label": "spam",
    "source_dataset": "SMS Spam Collection",
    "count": 264
  }
]

## Evaluation

Main metric: macro-F1 on the held-out test set.

| Model | Macro-F1 | Weighted-F1 | Avg latency ms | P95 latency ms | Cost |
|---|---:|---:|---:|---:|---:|
| Classical TF-IDF + Logistic Regression | 0.9432 | 0.9433 | 0.95 | 1.26 | 0 |
| Small DL MLP exported to ONNX | 0.9627 | 0.9626 | 2.92 | 6.71 | 0 |
| Hosted-API LLM zero-shot | macro-F1=0.7830, weighted-F1=0.7810, avg latency=1512.50 ms | | | | provider-priced |

## Per-class F1

Classical:

{
  "spam": 0.963855421686747,
  "question": 0.9135802469135802,
  "lead": 0.9620253164556962,
  "escalate": 0.9333333333333333
}

DL / ONNX:

{
  "spam": 0.9873417721518988,
  "question": 0.926829268292683,
  "lead": 0.9629629629629629,
  "escalate": 0.9736842105263158
}

## Deployment choice

- Shipped model: `classical`
- Serving method: `sklearn/joblib`
- Reason: Classical TF-IDF + Logistic Regression is within 0.02 macro-F1 of the DL model and is simpler, faster, cheaper, and easier to serve.

## Artifact hashes

{
  "classifier.joblib": "e4f16974584128d61a9a9a07f197d6de5624fc7901edd20ffcf656ececf3d2d3",
  "classifier.onnx": "a564404e55503a03b577cd8134994b59e7beca828134999b93d44cdef9423709",
  "dl_vectorizer.joblib": "7a2f8ff5168b6e114876c6ad69a994731425b35c12af280fef783dc5bc1b6185"
}

## Serving notes

The production model-server should load artifacts once at startup and refuse to boot if the artifact SHA-256 does not match this model card. The serving container must not include PyTorch, TensorFlow, or transformers.
