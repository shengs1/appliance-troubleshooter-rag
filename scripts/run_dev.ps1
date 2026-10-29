# scripts/run_dev.ps1
# ==============================================================================
# Windows Launcher cho He thong RAG Chatbot (FastAPI Backend + Chainlit UI)
# ==============================================================================

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = "utf-8"

$apiPort = 8000
$chainlitPort = 8001
$apiHost = "127.0.0.1"
$chainlitHost = "127.0.0.1"

Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "  KHOI DONG HE THONG RAG CHATBOT DIEN TU GIA DUNG (VIETNAMESE)" -ForegroundColor Cyan
Write-Host "======================================================================" -ForegroundColor Cyan

# 1. Kiem tra uv va moi truong
Write-Host "`n[1/4] Kiem tra moi truong thuc thi..." -ForegroundColor Yellow
$uvInstalled = Get-Command "uv" -ErrorAction SilentlyContinue
if (-not $uvInstalled) {
    Write-Host "[LOI] Khong tim thay 'uv'. Vui long cai dat uv hoac kich hoat moi truong ao!" -ForegroundColor Red
    exit 1
}
Write-Host "  -> Da tim thay uv tai: $($uvInstalled.Source)" -ForegroundColor Green

# Load bien moi truong tu file .env neu ton tai
if (Test-Path .env) {
    Get-Content .env | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
            $parts = $line.Split("=", 2)
            $varName = $parts[0].Trim()
            $varVal = $parts[1].Trim().Trim('"').Trim("'")
            if (-not [System.Environment]::GetEnvironmentVariable($varName, "Process")) {
                [System.Environment]::SetEnvironmentVariable($varName, $varVal, "Process")
            }
        }
    }
}

# Dam bao CHAINLIT_AUTH_SECRET luon ton tai de Chainlit Authentication khong loi
if (-not $env:CHAINLIT_AUTH_SECRET) {
    $env:CHAINLIT_AUTH_SECRET = "dev-chainlit-auth-secret-change-in-production-32chars"
}

# 2. Kiem tra va khoi tao Database
Write-Host "`n[2/4] Khoi tao co so du lieu SQLite (neu chua ton tai)..." -ForegroundColor Yellow
& uv run python -c "from rag_chatbot.database import init_db; init_db(); print('  -> SQLite Database da san sang.')"
if ($LASTEXITCODE -ne 0) {
    Write-Host "[LOI] Khoi tao co so du lieu that bai!" -ForegroundColor Red
    exit 1
}

# 3. Kiem tra va giai phong Port (neu bi chiem dung)
Write-Host "`n[3/4] Kiem tra va giai phong cong mang..." -ForegroundColor Yellow
function Free-Port([int]$port) {
    $conns = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
    if ($conns) {
        $pids = $conns | Select-Object -ExpandProperty OwningProcess -Unique
        foreach ($p in $pids) {
            if ($p -gt 0) {
                Write-Host "  -> Tu dong giai phong tien trinh chiem cong $port (PID: $p)..." -ForegroundColor Yellow
                & taskkill /PID $p /T /F 2>&1 | Out-Null
            }
        }
        Start-Sleep -Milliseconds 500
    }
}

Free-Port $apiPort
Free-Port $chainlitPort
Write-Host "  -> Cong API ($apiPort) va Cong Chainlit ($chainlitPort) da san sang." -ForegroundColor Green

# 4. Hien thi thong tin dich vu
Write-Host "`n[4/4] Cac dich vu va URL truy cap:" -ForegroundColor Yellow
Write-Host "  * Chainlit UI (Giao dien Chatbot duy nhat): http://$chainlitHost`:$chainlitPort" -ForegroundColor Cyan
Write-Host "  * Bang quan tri Admin chuyen dung:         http://$chainlitHost`:$chainlitPort/public/admin.html" -ForegroundColor Cyan
Write-Host "  * Trang Dang ky tai khoan moi:             http://$chainlitHost`:$chainlitPort/public/register.html" -ForegroundColor Cyan
Write-Host "  * Trang Quen mat khau:                     http://$chainlitHost`:$chainlitPort/public/forgot-password.html" -ForegroundColor Cyan
Write-Host "  * Trang Dat lai mat khau:                  http://$chainlitHost`:$chainlitPort/public/reset-password.html" -ForegroundColor Cyan
Write-Host "  * FastAPI Backend REST API / Swagger:       http://$apiHost`:$apiPort/docs" -ForegroundColor Cyan
Write-Host "  * Backend Health Check Endpoint:            http://$apiHost`:$apiPort/health" -ForegroundColor Cyan
Write-Host "`nNhan [Ctrl+C] de dung toan bo cac tien trinh." -ForegroundColor Gray
Write-Host "======================================================================" -ForegroundColor Cyan

# Khoi dong 2 tien trinh doc lap (Tat DEBUG flag cho Chainlit de khong spam websocket log)
$prevDebug = $env:DEBUG
$env:DEBUG = "false"
$fastApiProcess = Start-Process -FilePath "uv" -ArgumentList "run uvicorn rag_chatbot.main:app --host $apiHost --port $apiPort" -PassThru -NoNewWindow
$chainlitProcess = Start-Process -FilePath "uv" -ArgumentList "run chainlit run src/rag_chatbot/chainlit_app.py --host $chainlitHost --port $chainlitPort -h -w" -PassThru -NoNewWindow
$env:DEBUG = $prevDebug

try {
    # Cho tien trinh hoat dong
    while ($true) {
        Start-Sleep -Seconds 2
        if ($fastApiProcess.HasExited) {
            Write-Host "[THONG BAO] FastAPI da dung (ExitCode: $($fastApiProcess.ExitCode))." -ForegroundColor Yellow
            break
        }
        if ($chainlitProcess.HasExited) {
            Write-Host "[THONG BAO] Chainlit da dung (ExitCode: $($chainlitProcess.ExitCode))." -ForegroundColor Yellow
            break
        }
    }
}
finally {
    Write-Host "`nDang dung cac tien trinh nen..." -ForegroundColor Yellow
    if ($fastApiProcess -and -not $fastApiProcess.HasExited) {
        & taskkill /PID $fastApiProcess.Id /T /F 2>&1 | Out-Null
        Write-Host "  -> Da dung FastAPI (PID: $($fastApiProcess.Id))" -ForegroundColor Gray
    }
    if ($chainlitProcess -and -not $chainlitProcess.HasExited) {
        & taskkill /PID $chainlitProcess.Id /T /F 2>&1 | Out-Null
        Write-Host "  -> Da dung Chainlit (PID: $($chainlitProcess.Id))" -ForegroundColor Gray
    }
    Free-Port $apiPort
    Free-Port $chainlitPort
    Write-Host "He thong da tat hoan toan." -ForegroundColor Green
}
