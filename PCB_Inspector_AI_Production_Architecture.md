# PCB Inspector AI — Production Architecture & Implementation Plan

## 1. Product Overview

**PCB Inspector AI** is a production-grade, web-accessible computer-vision platform for AI-assisted visual inspection of printed circuit boards.

A user can:

1. Upload a PCB image.
2. Optionally provide an image URL.
3. Receive an AI-assisted inspection report.
4. View defect bounding boxes and confidence scores.
5. Review inspection history.
6. See model/version and inference metadata.

### Scope

The system detects **visible defects** in PCB imagery. It does **not** certify electrical correctness, functional correctness, or manufacturing compliance.

### Initial defect taxonomy

Start with a manageable taxonomy:

- Missing component
- Misaligned component
- Solder bridge
- Damaged component
- Surface/board damage
- Foreign object/debris
- Corrosion/contamination

The exact classes should be finalized after dataset exploration.

---

# 2. Production Architecture

```text
                         ┌─────────────────────────┐
                         │          USERS          │
                         │ Browser / Mobile Browser│
                         └────────────┬────────────┘
                                      │ HTTPS
                                      ▼
                         ┌─────────────────────────┐
                         │     Route 53 / DNS      │
                         └────────────┬────────────┘
                                      ▼
                         ┌─────────────────────────┐
                         │ CloudFront + WAF         │
                         └───────┬───────────┬─────┘
                                 │           │
                         ┌───────▼───┐   ┌──▼──────────┐
                         │ Frontend  │   │ API Gateway │
                         │ S3/React  │   │ / ALB       │
                         └───────────┘   └──────┬──────┘
                                                │
                                      ┌─────────▼─────────┐
                                      │ FastAPI Backend   │
                                      │ ECS/EKS           │
                                      └───────┬───────────┘
                                              │
                 ┌────────────────────────────┼─────────────────────────┐
                 │                            │                         │
                 ▼                            ▼                         ▼
          ┌──────────────┐             ┌──────────────┐         ┌──────────────┐
          │ PostgreSQL   │             │ S3           │         │ SQS          │
          │ RDS          │             │ Images       │         │ Job Queue    │
          └──────────────┘             └──────┬───────┘         └──────┬───────┘
                                               │                        │
                                               │                        ▼
                                               │              ┌──────────────────┐
                                               │              │ Inference Worker │
                                               │              │ EKS/ECS          │
                                               │              └────────┬─────────┘
                                               │                       │
                                               │                       ▼
                                               │              ┌──────────────────┐
                                               └─────────────►│ CV Model         │
                                                              │ YOLO / RT-DETR   │
                                                              └────────┬─────────┘
                                                                       │
                                                                       ▼
                                                              ┌──────────────────┐
                                                              │ Results / Events │
                                                              └────────┬─────────┘
                                                                       │
                                      ┌────────────────────────────────┼─────────────┐
                                      │                                │             │
                                      ▼                                ▼             ▼
                                  PostgreSQL                         S3          CloudWatch
                                      │
                                      ▼
                                  Dashboard


                 ─────────────── MLOps CONTROL PLANE ───────────────

 Dataset → Validation → Training → Evaluation → MLflow
                                             │
                                             ▼
                                       Model Registry
                                             │
                                      Approval Gate
                                             │
                                             ▼
                                     Model Deployment
                                             │
                                  Prometheus / Grafana
                                             │
                                      Drift Detection
                                             │
                                      Retraining Job
```

---

# 3. Recommended AWS Stack

| Layer | AWS Service | Purpose |
|---|---|---|
| DNS | Route 53 | Domain |
| CDN | CloudFront | Frontend/API edge delivery |
| Security | AWS WAF | Web protection |
| Frontend | S3 | React static hosting |
| Authentication | Cognito | User authentication |
| API | API Gateway or ALB | API entry point |
| Backend | ECS/Fargate or EKS | FastAPI services |
| Images | S3 | Original/processed images |
| Queue | SQS | Asynchronous inspection jobs |
| Database | RDS PostgreSQL | Users, jobs, detections, metadata |
| Container registry | ECR | Docker images |
| Secrets | Secrets Manager | Secrets/configuration |
| Model artifacts | S3 | Model weights/artifacts |
| Training | SageMaker Jobs or EKS Jobs | Model training |
| Model tracking | MLflow | Experiments/model versions |
| Monitoring | CloudWatch | AWS logs/metrics |
| Metrics | Prometheus | Application/model metrics |
| Visualization | Grafana | Operational/model dashboards |
| Notifications | SNS | Alerts |
| IaC | Terraform | Infrastructure |
| CI/CD | GitHub Actions | Build/test/deploy |
| IAM | IAM | Least-privilege access |
| Encryption | KMS | Encryption keys |

### ECS vs EKS

For a first production deployment, **ECS/Fargate** is simpler and cheaper.

For this portfolio project, however, **EKS is recommended if Kubernetes is a major skill you want to demonstrate**.

A practical approach:

- Development: Docker Compose
- Staging: ECS/Fargate
- Portfolio production: EKS

Do not introduce Kubernetes merely for complexity; use it where it demonstrates meaningful operational skills.

---

# 4. Core Services

## Frontend

React + TypeScript.

Responsibilities:

- Login/register
- Upload image
- Submit image URL
- Inspection progress
- Results visualization
- Bounding boxes
- Confidence scores
- Inspection history
- Model/version information
- Error handling

Suggested UI:

```text
PCB INSPECTOR AI

[ Upload PCB Image ]

        OR

[ Paste Image URL ]

        [ INSPECT PCB ]

-----------------------------------

Inspection #INS-92831

Status: COMPLETED

Overall Result: REVIEW REQUIRED

Defects:
  Solder Bridge       96.4%   Critical
  Missing Component   91.2%   Critical
  Misalignment        78.1%   High

[ View Annotated Image ]
[ Download Report ]
```

---

# 5. Backend Architecture

Use FastAPI.

Split responsibilities logically:

```text
API Gateway / ALB
       ↓
FastAPI
       ├── Auth
       ├── Upload Service
       ├── Inspection Service
       ├── Result Service
       ├── History Service
       └── Health/Metrics
```

The inference worker should be separate from the API.

### Why?

Inference can be CPU/GPU intensive and should not block API workers.

```text
API
 ↓
SQS
 ↓
Inference Worker
```

This also lets the inference fleet scale independently.

---

# 6. ML Architecture

## Model 1 — PCB Image Quality / Compatibility Classifier

Before defect detection:

```text
Image
 ↓
PCB classifier
 ↓
Is PCB? ── NO ──> Reject
 ↓ YES
Quality assessment
 ↓
Accept / Request better image
```

Possible quality checks:

- Blur
- Resolution
- Lighting
- PCB coverage
- Excessive angle
- Occlusion

This prevents obviously bad images from reaching the expensive detector.

---

## Model 2 — PCB Defect Detector

Start with:

**YOLO** for the first production baseline.

Candidate alternatives:

- YOLO-family detector
- RT-DETR
- Faster R-CNN
- DETR/ViT-based detector

Start with YOLO because it provides a strong speed/accuracy baseline and is straightforward to deploy.

Later compare it against RT-DETR.

### Inference output

```json
{
  "defect_type": "solder_bridge",
  "confidence": 0.964,
  "bbox": {
    "x1": 421,
    "y1": 183,
    "x2": 478,
    "y2": 229
  },
  "severity": "critical"
}
```

---

# 7. Confidence & Decision Engine

Do not make business decisions directly from raw model confidence.

Create a decision layer:

```text
Model Detection
      ↓
Confidence threshold
      ↓
Class-specific rules
      ↓
Severity calculation
      ↓
Inspection status
```

Example:

```text
confidence >= 0.90
    → HIGH CONFIDENCE

0.70–0.89
    → REVIEW

< 0.70
    → LOW CONFIDENCE / IGNORE
```

These thresholds must ultimately be calibrated against validation data.

---

# 8. Dataset Strategy

## Primary dataset sources

Start by evaluating public PCB defect datasets, especially:

### DeepPCB

A widely used benchmark/dataset for PCB defect detection.

Search for:

- DeepPCB
- PCB defect detection datasets
- PCB-AoI datasets

### Kaggle

Search for:

- PCB defect detection
- PCB inspection
- PCB faults
- PCB component detection

### Other research datasets

Search academic literature for:

- PCB AOI
- Automated Optical Inspection
- PCB defect detection
- PCB component inspection

**Important:** record the license/usage terms for every dataset.

Do not train a commercial/public-facing service on a dataset unless its license permits your intended use.

---

# 9. Dataset Pipeline

```text
Raw Dataset
    ↓
License verification
    ↓
Duplicate detection
    ↓
Image quality filtering
    ↓
Annotation validation
    ↓
Class balancing
    ↓
Train / Validation / Test
    ↓
Versioned dataset
```

Recommended dataset structure:

```text
data/
├── raw/
├── interim/
├── processed/
├── annotations/
└── splits/
```

Use DVC or another dataset-versioning mechanism.

---

# 10. Database Schema

Use PostgreSQL.

## users

```sql
users (
    id UUID PRIMARY KEY,
    email VARCHAR UNIQUE NOT NULL,
    cognito_sub VARCHAR UNIQUE,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
)
```

## inspections

```sql
inspections (
    id UUID PRIMARY KEY,
    user_id UUID REFERENCES users(id),
    image_key VARCHAR NOT NULL,
    status VARCHAR NOT NULL,
    overall_result VARCHAR,
    model_version VARCHAR,
    inference_time_ms INTEGER,
    created_at TIMESTAMP,
    completed_at TIMESTAMP
)
```

## detections

```sql
detections (
    id UUID PRIMARY KEY,
    inspection_id UUID REFERENCES inspections(id),
    defect_type VARCHAR NOT NULL,
    confidence FLOAT NOT NULL,
    severity VARCHAR,
    x1 FLOAT,
    y1 FLOAT,
    x2 FLOAT,
    y2 FLOAT,
    created_at TIMESTAMP
)
```

## models

```sql
models (
    id UUID PRIMARY KEY,
    name VARCHAR NOT NULL,
    version VARCHAR NOT NULL,
    artifact_uri VARCHAR,
    status VARCHAR,
    precision FLOAT,
    recall FLOAT,
    map50 FLOAT,
    created_at TIMESTAMP
)
```

## inspection_events

```sql
inspection_events (
    id UUID PRIMARY KEY,
    inspection_id UUID REFERENCES inspections(id),
    event_type VARCHAR NOT NULL,
    event_data JSONB,
    created_at TIMESTAMP
)
```

## api_usage

```sql
api_usage (
    id UUID PRIMARY KEY,
    user_id UUID REFERENCES users(id),
    endpoint VARCHAR,
    status_code INTEGER,
    latency_ms INTEGER,
    created_at TIMESTAMP
)
```

---

# 11. Object Storage Structure

S3:

```text
s3://pcb-inspector-prod/
│
├── uploads/
│   └── {user_id}/{inspection_id}/original.jpg
│
├── processed/
│   └── {inspection_id}/annotated.jpg
│
├── reports/
│   └── {inspection_id}/report.json
│
├── datasets/
│   ├── raw/
│   ├── processed/
│   └── versions/
│
├── models/
│   └── {model_name}/{version}/
│
└── mlflow/
```

Use separate buckets for sensitive production data if required.

Enable:

- Encryption
- Versioning
- Lifecycle policies
- Access logging where appropriate
- Block Public Access

---

# 12. API Design

Base:

```text
/api/v1
```

## Authentication

```http
POST /auth/signup
POST /auth/login
POST /auth/refresh
```

Cognito should ultimately handle authentication rather than implementing passwords yourself.

## Upload

```http
POST /inspections/upload
```

Returns:

```json
{
  "inspection_id": "INS-92831",
  "status": "QUEUED"
}
```

## Image URL

```http
POST /inspections/url
```

Request:

```json
{
  "image_url": "https://example.com/pcb.jpg"
}
```

The backend should:

1. Validate URL.
2. Restrict protocols.
3. Download with size/time limits.
4. Validate content type.
5. Validate image dimensions.
6. Scan/validate the image.
7. Store it in S3.
8. Create an inspection job.

## Status

```http
GET /inspections/{inspection_id}
```

Response:

```json
{
  "id": "INS-92831",
  "status": "COMPLETED",
  "overall_result": "REVIEW_REQUIRED",
  "model_version": "pcb-detector-1.4.0",
  "inference_time_ms": 82
}
```

## Results

```http
GET /inspections/{inspection_id}/results
```

## History

```http
GET /inspections
```

## Health

```http
GET /health
GET /ready
```

## Metrics

```http
GET /metrics
```

Prometheus-compatible metrics.

---

# 13. Asynchronous Inspection Lifecycle

```text
1. User uploads image

2. Backend validates image

3. Backend stores image in S3

4. Database creates inspection:
   status = QUEUED

5. Message sent to SQS

6. Worker receives job

7. Worker downloads image

8. Quality model runs

9. Defect detector runs

10. Business rules execute

11. Annotated image stored in S3

12. Results stored in PostgreSQL

13. Inspection status:
    COMPLETED

14. Frontend polls or receives status update
```

Failure path:

```text
Worker failure
     ↓
SQS retry
     ↓
Retry limit exceeded
     ↓
Dead Letter Queue
     ↓
Alert
```

---

# 14. Security

This should be treated as a real public application.

Implement:

- HTTPS everywhere
- AWS WAF
- Cognito authentication
- JWT validation
- IAM least privilege
- S3 Block Public Access
- S3 presigned upload URLs
- S3 encryption
- RDS encryption
- Secrets Manager
- Security groups
- Private subnets for backend/database
- Rate limiting
- Upload size limits
- MIME/content validation
- Image dimension limits
- URL download restrictions
- Request timeouts
- SQS DLQ
- Audit events

### SSRF protection

Because users can submit image URLs, URL ingestion is a security-sensitive feature.

Never blindly fetch arbitrary URLs.

Block:

- localhost
- private IP ranges
- loopback
- link-local addresses
- cloud metadata endpoints
- internal DNS targets

Only allow HTTP/HTTPS.

---

# 15. MLOps Pipeline

```text
                 DATA
                  │
                  ▼
            Data Validation
                  │
                  ▼
             DVC Version
                  │
                  ▼
              Training
                  │
                  ▼
             MLflow Run
                  │
                  ▼
              Evaluation
                  │
            ┌─────┴─────┐
            │            │
         FAIL           PASS
            │            │
            ▼            ▼
          Stop      Model Registry
                         │
                         ▼
                   Approval Gate
                         │
                         ▼
                    Build Image
                         │
                         ▼
                  Deploy to Staging
                         │
                         ▼
                 Integration Tests
                         │
                         ▼
                  Production Deploy
```

Track:

- mAP@50
- mAP@50:95
- Precision
- Recall
- F1
- Per-class AP
- Inference latency
- Model size
- GPU/CPU utilization

---

# 16. Model Monitoring

Prometheus metrics:

```text
model_inference_total
model_inference_latency_seconds
model_detection_total
model_low_confidence_total
model_errors_total
model_version_info
inspection_success_total
inspection_failure_total
```

Data monitoring:

```text
image_resolution_distribution
image_brightness_distribution
image_blur_score
class_distribution
confidence_distribution
```

Drift monitoring:

```text
Training image distribution
          vs
Production image distribution
```

Potential techniques:

- PSI
- KL divergence
- Wasserstein distance
- Embedding distribution drift

Start with simple statistical drift detection.

---

# 17. Grafana Dashboards

## Dashboard 1 — Application Health

```text
API Requests
Requests/min
Error Rate
p95 Latency
p99 Latency
5xx Rate
```

## Dashboard 2 — Inference

```text
Inspections/min
Average inference latency
p95 inference latency
GPU utilization
CPU utilization
Inference failures
Queue depth
```

## Dashboard 3 — Model Quality

```text
Detection count
Average confidence
Low-confidence percentage
Defect distribution
Per-class detection rate
Model version
```

## Dashboard 4 — Data Drift

```text
Brightness drift
Resolution drift
Image embedding drift
Defect distribution drift
Confidence drift
```

## Dashboard 5 — Business Metrics

```text
Total inspections
Passed inspections
Failed inspections
Review-required inspections
Defect rate
Most common defect
Daily active users
```

---

# 18. Alerting

Examples:

```text
API 5xx > 5% for 5 minutes
        ↓
SNS alert
```

```text
SQS queue depth > threshold
        ↓
Scale inference workers
```

```text
Inference p95 > 1 second
        ↓
Operational alert
```

```text
Data drift > threshold
        ↓
ML monitoring alert
```

```text
Model confidence distribution changes significantly
        ↓
Review dataset
```

---

# 19. CI/CD

Use GitHub Actions.

## Pull Request

```text
Developer PR
    ↓
Lint
    ↓
Unit Tests
    ↓
Type Checks
    ↓
Security Scan
    ↓
Docker Build
    ↓
Integration Tests
```

## Merge to main

```text
main
 ↓
Run tests
 ↓
Build Docker image
 ↓
Tag with Git SHA
 ↓
Push to ECR
 ↓
Terraform plan
 ↓
Deploy staging
 ↓
Smoke tests
 ↓
Approval
 ↓
Production
```

Never deploy using `latest` as the only production identifier.

Use immutable tags:

```text
pcb-api:7f91c2a
pcb-worker:7f91c2a
```

---

# 20. GitHub Actions Structure

```text
.github/
└── workflows/
    ├── ci.yml
    ├── backend.yml
    ├── frontend.yml
    ├── docker.yml
    ├── terraform.yml
    ├── model-training.yml
    └── security.yml
```

### Recommended checks

- Ruff
- Pytest
- MyPy
- ESLint
- TypeScript checks
- Trivy
- Dependabot
- Terraform fmt
- Terraform validate
- Terraform plan

Use GitHub OIDC to AWS instead of storing long-lived AWS access keys.

---

# 21. Terraform Structure

```text
infra/
├── environments/
│   ├── dev/
│   │   ├── main.tf
│   │   ├── variables.tf
│   │   └── terraform.tfvars
│   │
│   ├── staging/
│   └── prod/
│
└── modules/
    ├── networking/
    ├── eks/
    ├── rds/
    ├── s3/
    ├── sqs/
    ├── ecr/
    ├── cognito/
    ├── cloudfront/
    ├── waf/
    ├── iam/
    ├── secrets/
    ├── monitoring/
    └── route53/
```

State:

```text
Terraform
   ↓
S3 backend
   +
DynamoDB locking / appropriate Terraform backend locking
```

Use separate state per environment.

---

# 22. Repository Structure

```text
pcb-inspector-ai/
│
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   ├── pages/
│   │   ├── hooks/
│   │   ├── services/
│   │   └── types/
│   ├── public/
│   ├── Dockerfile
│   └── package.json
│
├── services/
│   ├── api/
│   │   ├── app/
│   │   │   ├── api/
│   │   │   ├── models/
│   │   │   ├── schemas/
│   │   │   ├── services/
│   │   │   ├── repositories/
│   │   │   ├── core/
│   │   │   └── main.py
│   │   ├── tests/
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   │
│   └── inference-worker/
│       ├── src/
│       │   ├── consumer/
│       │   ├── inference/
│       │   ├── preprocessing/
│       │   ├── postprocessing/
│       │   └── main.py
│       ├── tests/
│       └── Dockerfile
│
├── ml/
│   ├── data/
│   ├── preprocessing/
│   ├── training/
│   ├── evaluation/
│   ├── inference/
│   ├── monitoring/
│   ├── configs/
│   └── notebooks/
│
├── data/
│   ├── README.md
│   └── .gitkeep
│
├── infrastructure/
│   └── terraform/
│
├── k8s/
│   ├── namespaces/
│   ├── api/
│   ├── worker/
│   ├── ingress/
│   ├── autoscaling/
│   ├── prometheus/
│   └── grafana/
│
├── scripts/
│
├── docs/
│   ├── architecture.md
│   ├── api.md
│   ├── model.md
│   ├── deployment.md
│   └── security.md
│
├── .github/
│   └── workflows/
│
├── docker-compose.yml
├── Makefile
├── README.md
└── LICENSE
```

---

# 23. API/Worker Container Design

Do not put everything into one container.

Recommended:

```text
pcb-api
pcb-inference-worker
pcb-frontend
```

Later:

```text
pcb-training
pcb-data-validation
pcb-drift-monitor
```

This allows independent scaling.

---

# 24. Kubernetes Design

If using EKS:

```text
Namespace: pcb-prod

Deployments:
  pcb-api
  pcb-worker

Services:
  pcb-api

Ingress:
  ALB Ingress Controller

HPA:
  pcb-api
  pcb-worker

Config:
  ConfigMaps

Secrets:
  AWS Secrets Manager / External Secrets

Jobs:
  model-training
  data-validation
```

Worker autoscaling should consider SQS queue depth rather than only CPU.

---

# 25. Observability

Every inspection should have a correlation ID.

Example:

```text
inspection_id = INS-92831
request_id    = req-a91bc
trace_id      = trace-7192
model_version = pcb-detector-1.4.0
```

Log:

```json
{
  "event": "inspection_completed",
  "inspection_id": "INS-92831",
  "model_version": "1.4.0",
  "latency_ms": 82,
  "detections": 3
}
```

Use structured JSON logging.

---

# 26. Testing Strategy

## Unit

Test:

- Image validation
- Confidence calculations
- Severity rules
- API services
- Database repositories

## Integration

Test:

```text
API → S3 → SQS → Worker → DB
```

## ML

Test:

- Dataset integrity
- Model loading
- Prediction schema
- Regression metrics
- Per-class performance

## Load testing

Use Locust or k6.

Test:

```text
100 concurrent users
500 image uploads
SQS backlog
Inference latency
API p95
```

---

# 27. Cost Control

For the portfolio version, avoid running expensive GPU infrastructure 24/7.

Recommended:

- S3 for storage
- RDS PostgreSQL small instance
- EKS only if Kubernetes demonstration is important
- CPU inference initially if performance is acceptable
- GPU training only during training jobs
- Scale worker replicas to zero/low baseline when possible
- Lifecycle policies for old images
- CloudWatch log retention limits
- AWS Budgets alerts

A cheaper alternative is:

```text
CloudFront
   ↓
S3 frontend

ALB
   ↓
ECS/Fargate API

SQS
   ↓
ECS worker

RDS
```

Then migrate inference to GPU/EKS when required.

---

# 28. 6–8 Week Roadmap

## Week 1 — Research & Foundation

### Goals

- Finalize product requirements
- Research datasets
- Verify licenses
- Define defect taxonomy
- Build initial architecture
- Create GitHub repository
- Dockerize development environment

Deliverables:

```text
Architecture document
Dataset inventory
Initial repository
Docker Compose
FastAPI skeleton
React skeleton
```

---

# Week 2 — Dataset & Baseline ML

### Goals

- Download permitted datasets
- Clean data
- Validate annotations
- Create train/validation/test split
- Train baseline detector
- Establish evaluation metrics

Deliverables:

```text
Dataset v1
YOLO baseline
Evaluation report
Confusion matrix
Per-class metrics
MLflow experiments
```

Target:

```text
Establish baseline mAP
Establish baseline inference latency
```

Do not arbitrarily promise a particular accuracy before seeing the data.

---

# Week 3 — Inference Service

Build:

```text
FastAPI
   ↓
S3
   ↓
SQS
   ↓
Inference Worker
   ↓
Model
```

Implement:

- Image upload
- Image URL ingestion
- Validation
- Job creation
- Queue
- Worker
- Detection
- Annotated output
- Database persistence

Deliverable:

**End-to-end local inspection pipeline.**

---

# Week 4 — Frontend & Product Experience

Build:

- Landing page
- Upload interface
- URL interface
- Processing state
- Results page
- Bounding-box visualization
- Confidence/severity
- Inspection history
- Authentication

Deliverable:

**Complete local web application.**

---

# Week 5 — AWS Infrastructure

Implement Terraform for:

- VPC
- Subnets
- IAM
- S3
- ECR
- RDS
- SQS
- Secrets Manager
- Cognito
- CloudFront
- WAF

Deploy:

```text
Frontend
API
Worker
Database
Queue
Storage
```

Deliverable:

**Staging environment on AWS.**

---

# Week 6 — CI/CD + Kubernetes + Observability

Implement:

- GitHub Actions
- Docker build/push
- ECR
- Terraform pipeline
- EKS
- HPA
- Prometheus
- Grafana
- CloudWatch
- Structured logging

Deliverable:

**Automated deployment + production observability.**

---

# Week 7 — MLOps & Production Hardening

Implement:

- MLflow
- Model registry
- Dataset versioning
- Model version tracking
- Drift detection
- Automated evaluation
- Retraining workflow
- Security hardening
- Rate limiting
- SQS DLQ
- Error handling

Deliverable:

**Production-grade ML lifecycle.**

---

# Week 8 — Testing, Optimization & Portfolio

Implement:

- Load testing
- Security testing
- API tests
- ML regression tests
- Performance optimization
- Documentation
- Architecture diagrams
- Demo video
- Screenshots
- Resume bullets

Final deliverables:

```text
Live application
GitHub repository
Architecture diagram
API documentation
ML report
MLOps pipeline
Terraform infrastructure
Monitoring dashboards
Demo video
Technical documentation
```

---

# 29. Suggested Development Milestones

## MVP

```text
Upload
  ↓
Detect
  ↓
Results
```

## V1

```text
Authentication
History
URL ingestion
Annotated images
AWS deployment
```

## V2

```text
SQS
Async processing
Monitoring
CI/CD
Terraform
```

## V3

```text
MLflow
Model registry
Drift detection
Retraining
Kubernetes
Autoscaling
```

---

# 30. What Makes This Production Grade

The important distinction is:

### Basic project

```text
Image
 ↓
YOLO
 ↓
Bounding boxes
```

### This project

```text
                    ┌── Authentication
                    │
User → Frontend → API
                    │
                    ├── Validation
                    │
                    ├── S3
                    │
                    └── SQS
                         │
                         ▼
                     Inference
                         │
                    ┌────┴─────┐
                    │ CV Model │
                    └────┬─────┘
                         │
                    Decision Engine
                         │
             ┌───────────┼───────────┐
             ▼           ▼           ▼
            S3          DB       Metrics
             │           │           │
             └───────────┼───────────┘
                         ▼
                      Frontend

MLOps:
Dataset → Training → Evaluation → Registry → Deployment
                                      ↓
                                  Monitoring
                                      ↓
                                    Drift
                                      ↓
                                  Retraining
```

The project demonstrates:

- Computer Vision
- Deep Learning
- Backend engineering
- Distributed systems
- AWS
- Docker
- Kubernetes
- Terraform
- CI/CD
- MLOps
- Observability
- Security
- Database design
- System design

---

# 31. Resume Positioning

Use a project title such as:

**PCB Inspector AI — Production Computer Vision & MLOps Platform**

Possible resume bullets:

- Built a production-oriented PCB visual inspection platform using deep-learning object detection to identify and localize visible manufacturing defects from user-submitted images.
- Designed an asynchronous AWS architecture using S3, SQS, PostgreSQL, containerized FastAPI services and independently scalable inference workers.
- Implemented ML lifecycle management with dataset versioning, MLflow experiment tracking, model evaluation, versioned deployments and production drift monitoring.
- Provisioned AWS infrastructure using Terraform and automated application/container deployments through GitHub Actions CI/CD.
- Implemented Prometheus/Grafana and CloudWatch observability for API latency, inference performance, queue depth, model confidence and data-drift signals.

---

# 32. Important Product Limitations

The application should clearly communicate:

> **AI-assisted visual inspection only.**

It should not claim:

- Electrical testing
- Functional testing
- X-ray inspection
- Hidden solder-joint inspection
- Guaranteed manufacturing compliance
- Safety certification

This makes the product technically honest.

---

# 33. Recommended Final Technology Stack

```text
Frontend
────────
React
TypeScript
Tailwind CSS

Backend
───────
Python
FastAPI
SQLAlchemy
PostgreSQL

Computer Vision
───────────────
PyTorch
YOLO
OpenCV
Albumentations

MLOps
─────
MLflow
DVC
Prometheus
Grafana

Infrastructure
──────────────
Docker
Kubernetes
EKS
Terraform

AWS
───
S3
SQS
ECR
RDS
Cognito
CloudFront
Route 53
WAF
Secrets Manager
CloudWatch
SNS

CI/CD
─────
GitHub Actions
GitHub OIDC
Trivy
Pytest
Ruff
MyPy
```

---

# 34. Definition of Done

The project is complete when a new user can:

```text
1. Open the public website
2. Create an account
3. Upload a PCB image
4. Receive an inspection job ID
5. See processing status
6. Receive the inspection result
7. View annotated defects
8. See confidence and severity
9. View inspection history
10. Download a report
```

Meanwhile, an engineer can:

```text
1. Push code to GitHub
2. CI automatically tests it
3. Docker image is built
4. Image is pushed to ECR
5. Deployment runs automatically
6. Terraform manages infrastructure
7. Prometheus collects metrics
8. Grafana displays health
9. MLflow tracks models
10. Drift monitoring detects changes
11. Retraining can produce a new model
12. A controlled deployment promotes the model
```

That is the point at which **PCB Inspector AI becomes a portfolio-grade production ML system rather than simply a computer-vision model demo.**
