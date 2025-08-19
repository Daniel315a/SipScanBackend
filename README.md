# SipScanBackend

Backend de OCR construido con FastAPI para procesar documentos e imágenes, ejecutar OCR y entregar resultados estructurados a través de una API REST.

## Características

- Procesamiento de documentos e imágenes mediante OCR
- API RESTful con FastAPI
- Arquitectura por capas (routes, services, repositories)
- Documentación interactiva automática (Swagger/Redoc)
- Estructura modular y escalable

## Estructura del proyecto

```
SipScanBackend/
├── main.py              # Punto de entrada de la aplicación
├── routes/              # Manejadores de endpoints API
│   └── [archivos de rutas]
├── services/            # Lógica de negocio y reglas de aplicación
│   └── [archivos de servicios]
├── repositories/        # Acceso a datos y persistencia
│   └── [archivos de repositorios]
└── README.md           # Este archivo
```

## Inicio rápido

### 1. (Opcional) Crear y activar entorno virtual

```bash
python -m venv .venv

# Linux/macOS
source .venv/bin/activate

# Windows (PowerShell)
.venv\Scripts\Activate.ps1
```

### 2. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 3. Configurar variables de entorno

```bash
cp .env.example .env
# Editar el archivo .env con tus configuraciones
```

### 4. Ejecutar la aplicación

```bash
uvicorn main:app --reload --port 8000
```

### Acceso a la documentación

- **Swagger UI**: http://localhost:8000/docs
- **Redoc**: http://localhost:8000/redoc

## Arquitectura

La aplicación sigue un patrón de arquitectura por capas:

1. **Routes**: Manejan las solicitudes HTTP y responses
2. **Services**: Contienen la lógica de negocio principal
3. **Repositories**: Gestionan el acceso a datos y persistencia

## Flujo de trabajo con Git

### Ramas principales

- **main**: Rama de producción (protegida). Solo se aceptan PRs aprobados.
- **develop**: Rama de integración para cambios que irán en la próxima versión.

### Ramas de desarrollo

- **feature/***: Nuevas funcionalidades (se basan en develop → PR a develop)
- **hotfix/***: Correcciones críticas en producción (se basan en main → PR a main y retro-merge a develop)
- **release/*** (opcional): Estabilización previa a publicar en main
- **bugfix/*** (opcional): Correcciones no críticas (mismo flujo que feature)

### Flujo de trabajo

```
feature/* → develop → (release/* opcional) → main
hotfix/* → main → develop (retro-merge)
```

### Política de Pull Requests

- Un cambio por PR
- Descripción breve del cambio
- Referencia a issue relacionado (si aplica)
- Requiere al menos una aprobación
- Todos los checks deben pasar


