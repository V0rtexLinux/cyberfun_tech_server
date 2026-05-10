#!/bin/bash
# ========================================
# CYBER FUN ENDOSKELETON - Script de Instalação
# Execute: sudo bash install.sh
# ========================================

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}"
echo "╔══════════════════════════════════════════════════╗"
echo "║   CYBER FUN - Instalação Completa v3.0           ║"
echo "╚══════════════════════════════════════════════════╝"
echo -e "${NC}"

# Verificar se é root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}Execute com sudo: sudo bash install.sh${NC}"
    exit 1
fi

USER_HOME=$(eval echo ~${SUDO_USER})
INSTALL_DIR="$USER_HOME/cyberfun"

echo -e "${YELLOW}[1/8] Atualizando sistema...${NC}"
apt-get update -qq
apt-get upgrade -y -qq

echo -e "${YELLOW}[2/8] Instalando dependências do sistema...${NC}"
apt-get install -y \
    python3 python3-pip python3-venv python3-dev \
    espeak-ng libespeak-ng-dev \
    python3-pyaudio portaudio19-dev \
    mpg123 alsa-utils \
    libatlas-base-dev libhdf5-dev \
    libopencv-dev python3-opencv \
    git curl wget \
    i2c-tools \
    -qq

echo -e "${YELLOW}[3/8] Configurando interfaces (Serial, I2C, SPI)...${NC}"
# Serial
raspi-config nonint do_serial 0 || true
# I2C
raspi-config nonint do_i2c 0 || true
# Câmera
raspi-config nonint do_camera 0 || true

# Adicionar usuário ao grupo dialout (acesso serial)
usermod -a -G dialout,i2c,gpio,audio,video ${SUDO_USER}

echo -e "${YELLOW}[4/8] Criando ambiente Python...${NC}"
mkdir -p "$INSTALL_DIR"
cd "$INSTALL_DIR"
python3 -m venv venv
source venv/bin/activate

echo -e "${YELLOW}[5/8] Instalando dependências Python...${NC}"
pip install --upgrade pip -q
pip install -r requirements.txt -q

echo -e "${YELLOW}[6/8] Configurando serviço systemd...${NC}"
cat > /etc/systemd/system/cyberfun.service << EOF
[Unit]
Description=CyberFun Animatronic System v3.0
After=network.target sound.target

[Service]
Type=simple
User=${SUDO_USER}
WorkingDirectory=${INSTALL_DIR}
ExecStart=${INSTALL_DIR}/venv/bin/python3 Fredbear_system/main.py
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal
Environment="PYTHONPATH=${INSTALL_DIR}"

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable cyberfun.service

echo -e "${YELLOW}[7/8] Configurando áudio ALSA...${NC}"
cat > /home/${SUDO_USER}/.asoundrc << 'ALSA'
pcm.!default {
    type hw
    card 0
    device 0
}
ctl.!default {
    type hw
    card 0
}
ALSA

echo -e "${YELLOW}[8/8] Criando arquivo de configuração...${NC}"
cat > "$INSTALL_DIR/.env" << 'ENV'
# CyberFun v3.0 - Configuração
# Coloque sua chave OpenAI aqui para usar GPT-4o
OPENAI_API_KEY=

# Porta serial do Arduino (normalmente /dev/ttyACM0 ou /dev/ttyUSB0)
ARDUINO_PORT=/dev/ttyACM0

# Porta do servidor WebSocket
WS_PORT=8765
ENV

chown -R ${SUDO_USER}:${SUDO_USER} "$INSTALL_DIR"

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════╗"
echo "║   ✓ INSTALAÇÃO CONCLUÍDA!                        ║"
echo "╠══════════════════════════════════════════════════╣"
echo "║                                                  ║"
echo "║  Para iniciar:                                   ║"
echo "║    sudo systemctl start cyberfun                 ║"
echo "║                                                  ║"
echo "║  Para ver logs:                                  ║"
echo "║    journalctl -u cyberfun -f                     ║"
echo "║                                                  ║"
echo "║  Para iniciar manualmente:                       ║"
echo "║    cd ~/cyberfun                                 ║"
echo "║    source venv/bin/activate                      ║"
echo "║    python3 Fredbear_system/main.py               ║"
echo "║                                                  ║"
echo "║  REINICIE o Raspberry Pi para aplicar            ║"
echo "║  as configurações de interface!                  ║"
echo -e "╚══════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${YELLOW}Reiniciando em 10 segundos... (Ctrl+C para cancelar)${NC}"
sleep 10
reboot
