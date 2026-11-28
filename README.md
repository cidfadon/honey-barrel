# Honey-Barrel

Honey-Barrel is an intraday market and watchlist analysis agent (originally created by **[Marcin Bednarski](https://github.com/git-mb001)** and **[Jakub Bartnik](https://github.com/jakubbartnik)**) that evaluates intraday price fluctuations using a locally running Ollama model.

This fork adapts the setup for **Debian** after an Ubuntu compatibility issue with my motherboard caused system freezes, making Debian a practical and stable alternative for myself alongside the original Ubuntu setup.



## Installation Guide

I have tested this stack on both **Ubuntu 26.04.01** and **Debian 13.5.0** without major issues. Default user **`me`** was used originally for scripts default to `/home/me/git-repo/honey-barrel/workspace`. If you use a different directory layout, keep your paths and environment variables consistent across scripts and cron jobs.

I always like to start from a minimal headless installation with just SSH server and connect to my machine remotely, but if you feel more confortable using a desktop feel free to do it. Finish the installation and reboot the machine into Debian.

### Base OS & User Setup

1. Install Debian and while asked to create the new user, create a user named -> `me`. 
    
2. Add user `me` to sudoers: 

```bash
su -c "apt update && apt install -y sudo && usermod -aG sudo me"
```
Because this is a minimal installation, you will need to install sudo and add `me` to sudoers.
*LOGOUT OF YOUR SESSION AND LOGIN AGAIN*

3. Create the base folder and download the project:

```bash
sudo apt install -y git
mkdir -p ~/git-repo
cd ~/git-repo && git clone https://github.com/cidfadon/honey-barrel.git
```

### Install Ollama LLM

4. Install Ollama using curl

```bash
sudo apt install -y curl 
curl -fsSL https://ollama.com/install.sh | sh
```

At the end of the installation you should see something like NVIDIA or AMD GPU ready, otherwise a WARNING will be shown.

---
**NVIDIA USERS:**
Because most Nvidia drivers are propietary you have to add *contrib* to trixie main.

```bash
sudo sed -i 's/trixie main non-free-firmware/trixie main contrib non-free non-free-firmware/g' /etc/apt/sources.list
``` 

Make sure the command has added *contrib* and *non-free* to trixie main:

```bash
cat /etc/apt/sources.list.d/debian.sources /etc/apt/sources.list 2>/dev/null
```
Update your sources and install the Linux headers and download the nvidia driver:

```bash
sudo apt update && sudo apt install -y linux-headers-$(uname -r)
sudo apt install nvidia-driver
```
Now you have to reboot to load the new driver
```bash
sudo reboot
```

5. Download the following model and run a test query.  

```bash
ollama pull batiai/gemma4-e4b:q4
ollama list
ollama run batiai/gemma4-e4b:q4 "Sharing is caring. Reply in one short sentence."
ollama ps
```

You should see 100% GPU

```
me@debian:~/git-repo/honey-barrel$ ollama ps
NAME                    ID              SIZE      PROCESSOR    CONTEXT    RUNNER      UNTIL              
batiai/gemma4-e4b:q4    d682bf87e3a3    3.3 GB    100% GPU     131072     llamacpp    4 minutes from now
```

---
**RADEON USERS:**
In one of my tests, it happened to me that the model was running 100% CPU despite I have a 12GB Radeon and I got my card detected after Ollama installation. 

To solve this I had to add `ollama` to `render` and `video` groups and add `HSA_OVERRIDE_GFX_VERSION=10.3.0` to Ollama service as follows:

```bash
sudo usermod -aG render,video ollama 2>/dev/null || true
sudo mkdir -p /etc/systemd/system/ollama.service.d
printf '[Service]\nEnvironment="HSA_OVERRIDE_GFX_VERSION=10.3.0"\n' | sudo tee /etc/systemd/system/ollama.service.d/override.conf
```
If Ollama still uses CPU instead GPU try restarting Ollama service first:

```bash
sudo systemctl restart ollama
```
The reason is `ollama.service` might be initializating before `amdgpu` itself so `/dev/kfd` and `/dev/dri/renderD128` nodes are not yet there and `udev` is not 100% ready. To solve this, you have to check what rocm version Ollama is using the following command:

```bash
which ollama && ls -ld /usr/local/lib/ollama/rocm_* /usr/lib/ollama/rocm_* 2>/dev/null
```

Use that version for this other command:

```bash
sudo tee /etc/systemd/system/ollama.service.d/override.conf <<'EOF'
[Unit]
Wants=dev-kfd.device dev-dri-renderD128.device
After=dev-kfd.device dev-dri-renderD128.device

[Service]
Environment="HSA_OVERRIDE_GFX_VERSION=10.3.0"
Environment="HIP_VISIBLE_DEVICES=0"
Environment="OLLAMA_LLM_LIBRARY=your.rocm.version"
EOF
```
This should work.

### Install Javascript packet manager 

6. Install npm

```bash
sudo apt install -y npm
```

### Install Docker Engine

7. Set up Docker apt repository.

```bash
# Add Docker's official GPG key:
sudo apt update && sudo apt install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

# Add the repository to Apt sources:
sudo tee /etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/debian
Suites: $(. /etc/os-release && echo "$VERSION_CODENAME")
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF

sudo apt update
```

8. Install docker components

```bash
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

Please visit the official Docker site if you need more information: [https://docs.docker.com/engine/install/debian/](https://docs.docker.com/engine/install/debian/)

9. Add user me to docker group, so you can run docker with `me` user:

```bash
sudo usermod -aG docker me
```

*LOGOUT OF YOUR SESSION AND LOGIN AGAIN*

10. Check docker with `me` user:

```bash
docker ps
docker buildx ls
docker compose version
```

The results should look like this:

```
CONTAINER ID   IMAGE     COMMAND   CREATED   STATUS    PORTS     NAMES
NAME/NODE     DRIVER/ENDPOINT   STATUS    BUILDKIT   PLATFORMS
default*      docker
 \_ default    \_ default       running   v0.31.2    linux/amd64 (+3)
Docker Compose version v5.3.1
```

11. Create external volumes for Docker

```bash
docker volume create honey-barrel-stack_hermes_opt
docker volume create honey-barrel-stack_hermes_data
```

12. Setup folder permissions:
    
Set up the following variables:

```bash
export USER=me
export HOMEDIR=/home/me
export WORKSPACE=/home/me/git-repo/honey-barrel/workspace
```

Now set up permissionns:

```bash
mkdir -p $WORKSPACE
chown $USER:$USER -R $WORKSPACE $WORKSPACE/* 
chmod +x $WORKSPACE/scripts/*.sh

```
This step ensures that you have the appropriate permissions within your workspace.

13. Create custom environment file:
    
Within `/home/me/git-repo/honey-barrel/workspace` create a `.env` file with the following entries. 

```
# Visit https://github.com/settings/tokens and create a tocken for your account
GITHUB_TOKEN=your_token_here

# Visit https://app.alpaca.markets/ and sign up to get the following information
ALPACA_API_KEY_ID=your_key
ALPACA_API_SECRET_KEY=your_secret

# Enter your local IP address and model from ollama list output
OLLAMA_BASE_IP=your.local.ip.address
OLLAMA_BASE_URL=http://your.local.ip.address:11434
OLLAMA_MODEL=batiai/gemma4-e4b:q4
```

---
**NOTE:**
Make sure the Ollama model you have is the same you downloaded in the previous step. If you want to know the model just type:

```bash
ollama list
```

Expect a response like this:

```
NAME                    ID              SIZE      MODIFIED
batiai/gemma4-e4b:q4    d682bf87e3a3    5.3 GB    36 minutes ago
```

Copy and paste the `NAME` you get into your `.env` file.

## Starting the stack

14. Lets create the a full stack with the following coommand:

```bash
cd ~/git-repo/honey-barrel/workspace/scripts
./full_stack_recompose.sh
```

While asked, you always say `YES`. As a result you should see something like this at the end:

```
[+] build 6/6
 OK Image honey-barrel-stack-alpaca-mcp             Built    101.7s
 OK Image honey-barrel-stack-investment-analyst-api Built    101.7s
 OK Image honey-barrel-stack-hermes                 Built    101.7s
 OK Image honey-barrel-stack-mcp-toolbox            Built    101.7s
 OK Image honey-barrel-stack-stdio-terminal         Built    101.7s
 OK Image honey-barrel-stack-workspace-mcp          Built    101.7s
Do you wish to recreate containers even if their configuration haven't changed? [Y/N] Y

Continue with "recreate" option..
[+] up 10/10
 OK Network honey-barrel-stack_backend-net  Created    0.0s
 OK Network honey-barrel-stack_frontend-net Created    0.0s
 OK Network honey-barrel-stack_mcp-net      Created    0.0s
 OK Container alpaca-mcp                    Started   18.3s
 OK Container workspace                     Started   18.3s
 OK Container investment-analyst-api        Started   18.3s
 OK Container workspace-mcp                 Started   18.4s
 OK Container stdio-terminal                Started   18.3s
 OK Container mcp-toolbox                   Started   15.6s
 OK Container hermes                        Started
```
---
**HEADLESS LINUX:**
As you we are running a headless version of Debian, you cannot enter GUI locally, and you need to specify the following for Hermes to respond external queries:

Confirm which port hermes is responding:
```
grep -n -C 5 "18001" ~/git-repo/honey-barrel/workspace/docker-compose.yml
```
You should see something like this:
```
me@debian:~/git-repo/honey-barrel/workspace/scripts$ grep -n -C 5 "18001" ~/git-repo/honey-barrel/workspace/docker-compose.yml
242-      - backend-net
243-      - frontend-net          # so openclaw can reach it
244-
245-    ports:
246-      # Bound to loopback only — for direct API access and debugging.
247:      - "127.0.0.1:18001:8001"
248-
249-    healthcheck:
250-      test: ["CMD", "curl", "-fsS", "http://localhost:8001/health"]
251-      interval: 15s
252-      timeout: 5s
```
Change ``127.0.0.1`` for ``0.0.0.0`` and check again:

```
cd ~/git-repo/honey-barrel/workspace && sed -i 's/"127\.0\.0\.1:18001:8001"/"0.0.0.0:18001:8001"/' docker-compose.yml
grep -n -C 5 "18001" ~/git-repo/honey-barrel/workspace/docker-compose.yml
```
**WARNING** Now you should be able to get into the GUI from any other workstation using http://your.local.ip.address:18001/ui/ **if you share your private LAN with others DON'T DO THIS!**

Apply the changes:
```
docker compose up -d
ss -tlnp | grep 18001
```
---
**WORKAROUND:**
If you share your LAN with others you might want to keep your frontend local and prevent others to access your investments. You can create a tunnel on your client **not on the Honey-Barrel server** by running the following command:

```bash
ssh -N -L 8080:127.0.0.1:18001 me@your.honey-barrel.ip.address
```

A middle ground solution is to instal socat and redirect the whole traffic to an specific machine, so you can send it to a tablet and do not have to mess with console on smart devices, but the trade-off is **data will be sent in plain text** so anyone listening will see your packages.

```bash
sudo apt install -y socat
socat your.client.ip.address:8080,fork,reuseaddr TCP:127.0.0.1:18001
```

15. Finally we will create the MCP servers as follows:

```bash
docker compose exec hermes hermes mcp add analyst --url http://investment-analyst-api:8001/mcp
docker compose exec hermes hermes mcp add workspace --url http://workspace-mcp:3001/mcp
docker compose exec hermes hermes mcp add alpaca --url http://alpaca-mcp:3001/mcp
docker compose exec hermes hermes mcp add terminal --url http://stdio-terminal:3002/mcp
```

While connecting the servers you have to answer first ``n`` for authentication and then ``y`` to enable all the tools:

```
Connecting to http://investment-analyst-api:8001/mcp
Does this server require authentication? [Y/n]: n
Enable all 9 tools? [Y/n/select]: y

Does this server require authentication? [Y/n]: n
Enable all 6 tools? [Y/n/select]: y

Connecting to http://alpaca-mcp:3001/mcp
Does this server require authentication? [Y/n]: n
Enable all 12 tools? [Y/n/select]: Y

Connecting to http://stdio-terminal:3002/mcp
Does this server require authentication? [Y/n]: n
Enable all 1 tools? [Y/n/select]: y
```

## Last step: Enable crons

16. Copy/paste as `crontab_me_start.bak`

```
CRON_TZ=Europe/Dublin

 0,11,22,33,44,55 14-21 * * 1-5 cd /home/me/git-repo/honey-barrel/workspace && LOCK_WAIT_SECONDS=120 MAX_PARAREL_CRONTASKS_RUN=5 WATCHLIST_TICKERS='AAL'   HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=false HERMES_PERSISTENT_READY_WARMUP=false TIMEOUT_RETEST_ATTEMPTS=0 RUN_TIMEOUT_SECONDS=1500 DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true DIRECT_ALPACA_ONLY_MODE=false /home/me/git-repo/honey-barrel/workspace/scripts/daily_investment_watchlist_report_generator.sh --run-now >> /home/me/git-repo/honey-barrel/workspace/reports/.cron_state/cron_AAL.log 2>&1 # Daily Investment Watchlist Report Generator:AAL
 1,12,23,34,45,56 14-21 * * 1-5 cd /home/me/git-repo/honey-barrel/workspace && LOCK_WAIT_SECONDS=120 MAX_PARAREL_CRONTASKS_RUN=5 WATCHLIST_TICKERS='AAPL'  HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=false HERMES_PERSISTENT_READY_WARMUP=false TIMEOUT_RETEST_ATTEMPTS=0 RUN_TIMEOUT_SECONDS=1500 DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true DIRECT_ALPACA_ONLY_MODE=false /home/me/git-repo/honey-barrel/workspace/scripts/daily_investment_watchlist_report_generator.sh --run-now >> /home/me/git-repo/honey-barrel/workspace/reports/.cron_state/cron_AAPL.log 2>&1 # Daily Investment Watchlist Report Generator:AAPL
 2,13,24,35,46,57 14-21 * * 1-5 cd /home/me/git-repo/honey-barrel/workspace && LOCK_WAIT_SECONDS=120 MAX_PARAREL_CRONTASKS_RUN=5 WATCHLIST_TICKERS='ACHR'  HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=false HERMES_PERSISTENT_READY_WARMUP=false TIMEOUT_RETEST_ATTEMPTS=0 RUN_TIMEOUT_SECONDS=1500 DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true DIRECT_ALPACA_ONLY_MODE=false /home/me/git-repo/honey-barrel/workspace/scripts/daily_investment_watchlist_report_generator.sh --run-now >> /home/me/git-repo/honey-barrel/workspace/reports/.cron_state/cron_ACHR.log 2>&1 # Daily Investment Watchlist Report Generator:ACHR
 3,14,25,36,47,58 14-21 * * 1-5 cd /home/me/git-repo/honey-barrel/workspace && LOCK_WAIT_SECONDS=120 MAX_PARAREL_CRONTASKS_RUN=5 WATCHLIST_TICKERS='AFRM'  HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=false HERMES_PERSISTENT_READY_WARMUP=false TIMEOUT_RETEST_ATTEMPTS=0 RUN_TIMEOUT_SECONDS=1500 DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true DIRECT_ALPACA_ONLY_MODE=false /home/me/git-repo/honey-barrel/workspace/scripts/daily_investment_watchlist_report_generator.sh --run-now >> /home/me/git-repo/honey-barrel/workspace/reports/.cron_state/cron_AFRM.log 2>&1 # Daily Investment Watchlist Report Generator:AFRM
 4,15,26,37,48,59 14-21 * * 1-5 cd /home/me/git-repo/honey-barrel/workspace && LOCK_WAIT_SECONDS=120 MAX_PARAREL_CRONTASKS_RUN=5 WATCHLIST_TICKERS='ALAB'  HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=false HERMES_PERSISTENT_READY_WARMUP=false TIMEOUT_RETEST_ATTEMPTS=0 RUN_TIMEOUT_SECONDS=1500 DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true DIRECT_ALPACA_ONLY_MODE=false /home/me/git-repo/honey-barrel/workspace/scripts/daily_investment_watchlist_report_generator.sh --run-now >> /home/me/git-repo/honey-barrel/workspace/reports/.cron_state/cron_ALAB.log 2>&1 # Daily Investment Watchlist Report Generator:ALAB
 5,16,27,38,49    14-21 * * 1-5 cd /home/me/git-repo/honey-barrel/workspace && LOCK_WAIT_SECONDS=120 MAX_PARAREL_CRONTASKS_RUN=5 WATCHLIST_TICKERS='AMBA'  HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=false HERMES_PERSISTENT_READY_WARMUP=false TIMEOUT_RETEST_ATTEMPTS=0 RUN_TIMEOUT_SECONDS=1500 DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true DIRECT_ALPACA_ONLY_MODE=false /home/me/git-repo/honey-barrel/workspace/scripts/daily_investment_watchlist_report_generator.sh --run-now >> /home/me/git-repo/honey-barrel/workspace/reports/.cron_state/cron_AMBA.log 2>&1 # Daily Investment Watchlist Report Generator:AMBA
 6,17,28,39,50    14-21 * * 1-5 cd /home/me/git-repo/honey-barrel/workspace && LOCK_WAIT_SECONDS=120 MAX_PARAREL_CRONTASKS_RUN=5 WATCHLIST_TICKERS='AMD'   HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=false HERMES_PERSISTENT_READY_WARMUP=false TIMEOUT_RETEST_ATTEMPTS=0 RUN_TIMEOUT_SECONDS=1500 DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true DIRECT_ALPACA_ONLY_MODE=false /home/me/git-repo/honey-barrel/workspace/scripts/daily_investment_watchlist_report_generator.sh --run-now >> /home/me/git-repo/honey-barrel/workspace/reports/.cron_state/cron_AMD.log 2>&1 # Daily Investment Watchlist Report Generator:AMD
 7,18,29,40,51    14-21 * * 1-5 cd /home/me/git-repo/honey-barrel/workspace && LOCK_WAIT_SECONDS=120 MAX_PARAREL_CRONTASKS_RUN=5 WATCHLIST_TICKERS='AMZN'  HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=false HERMES_PERSISTENT_READY_WARMUP=false TIMEOUT_RETEST_ATTEMPTS=0 RUN_TIMEOUT_SECONDS=1500 DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true DIRECT_ALPACA_ONLY_MODE=false /home/me/git-repo/honey-barrel/workspace/scripts/daily_investment_watchlist_report_generator.sh --run-now >> /home/me/git-repo/honey-barrel/workspace/reports/.cron_state/cron_AMZN.log 2>&1 # Daily Investment Watchlist Report Generator:AMZN
 8,19,30,41,52    14-21 * * 1-5 cd /home/me/git-repo/honey-barrel/workspace && LOCK_WAIT_SECONDS=120 MAX_PARAREL_CRONTASKS_RUN=5 WATCHLIST_TICKERS='APLD'  HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=false HERMES_PERSISTENT_READY_WARMUP=false TIMEOUT_RETEST_ATTEMPTS=0 RUN_TIMEOUT_SECONDS=1500 DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true DIRECT_ALPACA_ONLY_MODE=false /home/me/git-repo/honey-barrel/workspace/scripts/daily_investment_watchlist_report_generator.sh --run-now >> /home/me/git-repo/honey-barrel/workspace/reports/.cron_state/cron_APLD.log 2>&1 # Daily Investment Watchlist Report Generator:APLD
 9,20,31,42,53    14-21 * * 1-5 cd /home/me/git-repo/honey-barrel/workspace && LOCK_WAIT_SECONDS=120 MAX_PARAREL_CRONTASKS_RUN=5 WATCHLIST_TICKERS='ASTH'  HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=false HERMES_PERSISTENT_READY_WARMUP=false TIMEOUT_RETEST_ATTEMPTS=0 RUN_TIMEOUT_SECONDS=1500 DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true DIRECT_ALPACA_ONLY_MODE=false /home/me/git-repo/honey-barrel/workspace/scripts/daily_investment_watchlist_report_generator.sh --run-now >> /home/me/git-repo/honey-barrel/workspace/reports/.cron_state/cron_ASTH.log 2>&1 # Daily Investment Watchlist Report Generator:ASTH
10,21,32,43,54    14-21 * * 1-5 cd /home/me/git-repo/honey-barrel/workspace && LOCK_WAIT_SECONDS=120 MAX_PARAREL_CRONTASKS_RUN=5 WATCHLIST_TICKERS='BIVI'  HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=false HERMES_PERSISTENT_READY_WARMUP=false TIMEOUT_RETEST_ATTEMPTS=0 RUN_TIMEOUT_SECONDS=1500 DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true DIRECT_ALPACA_ONLY_MODE=false /home/me/git-repo/honey-barrel/workspace/scripts/daily_investment_watchlist_report_generator.sh --run-now >> /home/me/git-repo/honey-barrel/workspace/reports/.cron_state/cron_BIVI.log 2>&1 # Daily Investment Watchlist Report Generator:BIVI
 0,11,22,33,44,55 14-21 * * 1-5 cd /home/me/git-repo/honey-barrel/workspace && LOCK_WAIT_SECONDS=120 MAX_PARAREL_CRONTASKS_RUN=5 WATCHLIST_TICKERS='BLD'   HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=false HERMES_PERSISTENT_READY_WARMUP=false TIMEOUT_RETEST_ATTEMPTS=0 RUN_TIMEOUT_SECONDS=1500 DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true DIRECT_ALPACA_ONLY_MODE=false /home/me/git-repo/honey-barrel/workspace/scripts/daily_investment_watchlist_report_generator.sh --run-now >> /home/me/git-repo/honey-barrel/workspace/reports/.cron_state/cron_BLD.log 2>&1 # Daily Investment Watchlist Report Generator:BLD
 1,12,23,34,45,56 14-21 * * 1-5 cd /home/me/git-repo/honey-barrel/workspace && LOCK_WAIT_SECONDS=120 MAX_PARAREL_CRONTASKS_RUN=5 WATCHLIST_TICKERS='BTDR'  HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=false HERMES_PERSISTENT_READY_WARMUP=false TIMEOUT_RETEST_ATTEMPTS=0 RUN_TIMEOUT_SECONDS=1500 DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true DIRECT_ALPACA_ONLY_MODE=false /home/me/git-repo/honey-barrel/workspace/scripts/daily_investment_watchlist_report_generator.sh --run-now >> /home/me/git-repo/honey-barrel/workspace/reports/.cron_state/cron_BTDR.log 2>&1 # Daily Investment Watchlist Report Generator:BTDR
 2,13,24,35,46,57 14-21 * * 1-5 cd /home/me/git-repo/honey-barrel/workspace && LOCK_WAIT_SECONDS=120 MAX_PARAREL_CRONTASKS_RUN=5 WATCHLIST_TICKERS='CAN'   HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=false HERMES_PERSISTENT_READY_WARMUP=false TIMEOUT_RETEST_ATTEMPTS=0 RUN_TIMEOUT_SECONDS=1500 DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true DIRECT_ALPACA_ONLY_MODE=false /home/me/git-repo/honey-barrel/workspace/scripts/daily_investment_watchlist_report_generator.sh --run-now >> /home/me/git-repo/honey-barrel/workspace/reports/.cron_state/cron_CAN.log 2>&1 # Daily Investment Watchlist Report Generator:CAN
 3,14,25,36,47,58 14-21 * * 1-5 cd /home/me/git-repo/honey-barrel/workspace && LOCK_WAIT_SECONDS=120 MAX_PARAREL_CRONTASKS_RUN=5 WATCHLIST_TICKERS='CHPT'  HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=false HERMES_PERSISTENT_READY_WARMUP=false TIMEOUT_RETEST_ATTEMPTS=0 RUN_TIMEOUT_SECONDS=1500 DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true DIRECT_ALPACA_ONLY_MODE=false /home/me/git-repo/honey-barrel/workspace/scripts/daily_investment_watchlist_report_generator.sh --run-now >> /home/me/git-repo/honey-barrel/workspace/reports/.cron_state/cron_CHPT.log 2>&1 # Daily Investment Watchlist Report Generator:CHPT
 4,15,26,37,48,59 14-21 * * 1-5 cd /home/me/git-repo/honey-barrel/workspace && LOCK_WAIT_SECONDS=120 MAX_PARAREL_CRONTASKS_RUN=5 WATCHLIST_TICKERS='CIFR'  HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=false HERMES_PERSISTENT_READY_WARMUP=false TIMEOUT_RETEST_ATTEMPTS=0 RUN_TIMEOUT_SECONDS=1500 DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true DIRECT_ALPACA_ONLY_MODE=false /home/me/git-repo/honey-barrel/workspace/scripts/daily_investment_watchlist_report_generator.sh --run-now >> /home/me/git-repo/honey-barrel/workspace/reports/.cron_state/cron_CIFR.log 2>&1 # Daily Investment Watchlist Report Generator:CIFR
 5,16,27,38,49    14-21 * * 1-5 cd /home/me/git-repo/honey-barrel/workspace && LOCK_WAIT_SECONDS=120 MAX_PARAREL_CRONTASKS_RUN=5 WATCHLIST_TICKERS='CLSK'  HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=false HERMES_PERSISTENT_READY_WARMUP=false TIMEOUT_RETEST_ATTEMPTS=0 RUN_TIMEOUT_SECONDS=1500 DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true DIRECT_ALPACA_ONLY_MODE=false /home/me/git-repo/honey-barrel/workspace/scripts/daily_investment_watchlist_report_generator.sh --run-now >> /home/me/git-repo/honey-barrel/workspace/reports/.cron_state/cron_CLSK.log 2>&1 # Daily Investment Watchlist Report Generator:CLSK
 6,17,28,39,50    14-21 * * 1-5 cd /home/me/git-repo/honey-barrel/workspace && LOCK_WAIT_SECONDS=120 MAX_PARAREL_CRONTASKS_RUN=5 WATCHLIST_TICKERS='COHR'  HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=false HERMES_PERSISTENT_READY_WARMUP=false TIMEOUT_RETEST_ATTEMPTS=0 RUN_TIMEOUT_SECONDS=1500 DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true DIRECT_ALPACA_ONLY_MODE=false /home/me/git-repo/honey-barrel/workspace/scripts/daily_investment_watchlist_report_generator.sh --run-now >> /home/me/git-repo/honey-barrel/workspace/reports/.cron_state/cron_COHR.log 2>&1 # Daily Investment Watchlist Report Generator:COHR
 7,18,29,40,51    14-21 * * 1-5 cd /home/me/git-repo/honey-barrel/workspace && LOCK_WAIT_SECONDS=120 MAX_PARAREL_CRONTASKS_RUN=5 WATCHLIST_TICKERS='CORZ'  HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=false HERMES_PERSISTENT_READY_WARMUP=false TIMEOUT_RETEST_ATTEMPTS=0 RUN_TIMEOUT_SECONDS=1500 DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true DIRECT_ALPACA_ONLY_MODE=false /home/me/git-repo/honey-barrel/workspace/scripts/daily_investment_watchlist_report_generator.sh --run-now >> /home/me/git-repo/honey-barrel/workspace/reports/.cron_state/cron_CORZ.log 2>&1 # Daily Investment Watchlist Report Generator:CORZ
 8,19,30,41,52    14-21 * * 1-5 cd /home/me/git-repo/honey-barrel/workspace && LOCK_WAIT_SECONDS=120 MAX_PARAREL_CRONTASKS_RUN=5 WATCHLIST_TICKERS='CRDOC' HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=false HERMES_PERSISTENT_READY_WARMUP=false TIMEOUT_RETEST_ATTEMPTS=0 RUN_TIMEOUT_SECONDS=1500 DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true DIRECT_ALPACA_ONLY_MODE=false /home/me/git-repo/honey-barrel/workspace/scripts/daily_investment_watchlist_report_generator.sh --run-now >> /home/me/git-repo/honey-barrel/workspace/reports/.cron_state/cron_CRDOC.log 2>&1 # Daily Investment Watchlist Report Generator:CRDOC
 9,20,31,42,53    14-21 * * 1-5 cd /home/me/git-repo/honey-barrel/workspace && LOCK_WAIT_SECONDS=120 MAX_PARAREL_CRONTASKS_RUN=5 WATCHLIST_TICKERS='CRSP'  HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=false HERMES_PERSISTENT_READY_WARMUP=false TIMEOUT_RETEST_ATTEMPTS=0 RUN_TIMEOUT_SECONDS=1500 DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true DIRECT_ALPACA_ONLY_MODE=false /home/me/git-repo/honey-barrel/workspace/scripts/daily_investment_watchlist_report_generator.sh --run-now >> /home/me/git-repo/honey-barrel/workspace/reports/.cron_state/cron_CRSP.log 2>&1 # Daily Investment Watchlist Report Generator:CRSP
10,21,32,43,54    14-21 * * 1-5 cd /home/me/git-repo/honey-barrel/workspace && LOCK_WAIT_SECONDS=120 MAX_PARAREL_CRONTASKS_RUN=5 WATCHLIST_TICKERS='CVNA'  HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=false HERMES_PERSISTENT_READY_WARMUP=false TIMEOUT_RETEST_ATTEMPTS=0 RUN_TIMEOUT_SECONDS=1500 DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true DIRECT_ALPACA_ONLY_MODE=false /home/me/git-repo/honey-barrel/workspace/scripts/daily_investment_watchlist_report_generator.sh --run-now >> /home/me/git-repo/honey-barrel/workspace/reports/.cron_state/cron_CVNA.log 2>&1 # Daily Investment Watchlist Report Generator:CVNA
 0,11,22,33,44,55 14-21 * * 1-5 cd /home/me/git-repo/honey-barrel/workspace && LOCK_WAIT_SECONDS=120 MAX_PARAREL_CRONTASKS_RUN=5 WATCHLIST_TICKERS='DMRA'  HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=false HERMES_PERSISTENT_READY_WARMUP=false TIMEOUT_RETEST_ATTEMPTS=0 RUN_TIMEOUT_SECONDS=1500 DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true DIRECT_ALPACA_ONLY_MODE=false /home/me/git-repo/honey-barrel/workspace/scripts/daily_investment_watchlist_report_generator.sh --run-now >> /home/me/git-repo/honey-barrel/workspace/reports/.cron_state/cron_DMRA.log 2>&1 # Daily Investment Watchlist Report Generator:DMRA
 1,12,23,34,45,56 14-21 * * 1-5 cd /home/me/git-repo/honey-barrel/workspace && LOCK_WAIT_SECONDS=120 MAX_PARAREL_CRONTASKS_RUN=5 WATCHLIST_TICKERS='ELF'   HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=false HERMES_PERSISTENT_READY_WARMUP=false TIMEOUT_RETEST_ATTEMPTS=0 RUN_TIMEOUT_SECONDS=1500 DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true DIRECT_ALPACA_ONLY_MODE=false /home/me/git-repo/honey-barrel/workspace/scripts/daily_investment_watchlist_report_generator.sh --run-now >> /home/me/git-repo/honey-barrel/workspace/reports/.cron_state/cron_ELF.log 2>&1 # Daily Investment Watchlist Report Generator:ELF
 2,13,24,35,46,57 14-21 * * 1-5 cd /home/me/git-repo/honey-barrel/workspace && LOCK_WAIT_SECONDS=120 MAX_PARAREL_CRONTASKS_RUN=5 WATCHLIST_TICKERS='ESTC'  HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=false HERMES_PERSISTENT_READY_WARMUP=false TIMEOUT_RETEST_ATTEMPTS=0 RUN_TIMEOUT_SECONDS=1500 DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true DIRECT_ALPACA_ONLY_MODE=false /home/me/git-repo/honey-barrel/workspace/scripts/daily_investment_watchlist_report_generator.sh --run-now >> /home/me/git-repo/honey-barrel/workspace/reports/.cron_state/cron_ESTC.log 2>&1 # Daily Investment Watchlist Report Generator:ESTC
 3,14,25,36,47,58 14-21 * * 1-5 cd /home/me/git-repo/honey-barrel/workspace && LOCK_WAIT_SECONDS=120 MAX_PARAREL_CRONTASKS_RUN=5 WATCHLIST_TICKERS='GHRS'  HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=false HERMES_PERSISTENT_READY_WARMUP=false TIMEOUT_RETEST_ATTEMPTS=0 RUN_TIMEOUT_SECONDS=1500 DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true DIRECT_ALPACA_ONLY_MODE=false /home/me/git-repo/honey-barrel/workspace/scripts/daily_investment_watchlist_report_generator.sh --run-now >> /home/me/git-repo/honey-barrel/workspace/reports/.cron_state/cron_GHRS.log 2>&1 # Daily Investment Watchlist Report Generator:GHRS
 4,15,26,37,48,59 14-21 * * 1-5 cd /home/me/git-repo/honey-barrel/workspace && LOCK_WAIT_SECONDS=120 MAX_PARAREL_CRONTASKS_RUN=5 WATCHLIST_TICKERS='GOOGL' HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=false HERMES_PERSISTENT_READY_WARMUP=false TIMEOUT_RETEST_ATTEMPTS=0 RUN_TIMEOUT_SECONDS=1500 DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true DIRECT_ALPACA_ONLY_MODE=false /home/me/git-repo/honey-barrel/workspace/scripts/daily_investment_watchlist_report_generator.sh --run-now >> /home/me/git-repo/honey-barrel/workspace/reports/.cron_state/cron_GOOGL.log 2>&1 # Daily Investment Watchlist Report Generator:GOOGL
 5,16,27,38,49    14-21 * * 1-5 cd /home/me/git-repo/honey-barrel/workspace && LOCK_WAIT_SECONDS=120 MAX_PARAREL_CRONTASKS_RUN=5 WATCHLIST_TICKERS='HE'    HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=false HERMES_PERSISTENT_READY_WARMUP=false TIMEOUT_RETEST_ATTEMPTS=0 RUN_TIMEOUT_SECONDS=1500 DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true DIRECT_ALPACA_ONLY_MODE=false /home/me/git-repo/honey-barrel/workspace/scripts/daily_investment_watchlist_report_generator.sh --run-now >> /home/me/git-repo/honey-barrel/workspace/reports/.cron_state/cron_HE.log 2>&1 # Daily Investment Watchlist Report Generator:HE
 6,17,28,39,50    14-21 * * 1-5 cd /home/me/git-repo/honey-barrel/workspace && LOCK_WAIT_SECONDS=120 MAX_PARAREL_CRONTASKS_RUN=5 WATCHLIST_TICKERS='HIMS'  HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=false HERMES_PERSISTENT_READY_WARMUP=false TIMEOUT_RETEST_ATTEMPTS=0 RUN_TIMEOUT_SECONDS=1500 DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true DIRECT_ALPACA_ONLY_MODE=false /home/me/git-repo/honey-barrel/workspace/scripts/daily_investment_watchlist_report_generator.sh --run-now >> /home/me/git-repo/honey-barrel/workspace/reports/.cron_state/cron_HIMS.log 2>&1 # Daily Investment Watchlist Report Generator:HIMS
 7,18,29,40,51    14-21 * * 1-5 cd /home/me/git-repo/honey-barrel/workspace && LOCK_WAIT_SECONDS=120 MAX_PARAREL_CRONTASKS_RUN=5 WATCHLIST_TICKERS='HOOD'  HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=false HERMES_PERSISTENT_READY_WARMUP=false TIMEOUT_RETEST_ATTEMPTS=0 RUN_TIMEOUT_SECONDS=1500 DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true DIRECT_ALPACA_ONLY_MODE=false /home/me/git-repo/honey-barrel/workspace/scripts/daily_investment_watchlist_report_generator.sh --run-now >> /home/me/git-repo/honey-barrel/workspace/reports/.cron_state/cron_HOOD.log 2>&1 # Daily Investment Watchlist Report Generator:HOOD
 8,19,30,41,52    14-21 * * 1-5 cd /home/me/git-repo/honey-barrel/workspace && LOCK_WAIT_SECONDS=120 MAX_PARAREL_CRONTASKS_RUN=5 WATCHLIST_TICKERS='HUT'   HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=false HERMES_PERSISTENT_READY_WARMUP=false TIMEOUT_RETEST_ATTEMPTS=0 RUN_TIMEOUT_SECONDS=1500 DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true DIRECT_ALPACA_ONLY_MODE=false /home/me/git-repo/honey-barrel/workspace/scripts/daily_investment_watchlist_report_generator.sh --run-now >> /home/me/git-repo/honey-barrel/workspace/reports/.cron_state/cron_HUT.log 2>&1 # Daily Investment Watchlist Report Generator:HUT
 9,20,31,42,53    14-21 * * 1-5 cd /home/me/git-repo/honey-barrel/workspace && LOCK_WAIT_SECONDS=120 MAX_PARAREL_CRONTASKS_RUN=5 WATCHLIST_TICKERS='IOVA'  HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=false HERMES_PERSISTENT_READY_WARMUP=false TIMEOUT_RETEST_ATTEMPTS=0 RUN_TIMEOUT_SECONDS=1500 DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true DIRECT_ALPACA_ONLY_MODE=false /home/me/git-repo/honey-barrel/workspace/scripts/daily_investment_watchlist_report_generator.sh --run-now >> /home/me/git-repo/honey-barrel/workspace/reports/.cron_state/cron_IOVA.log 2>&1 # Daily Investment Watchlist Report Generator:IOVA
10,21,32,43,54    14-21 * * 1-5 cd /home/me/git-repo/honey-barrel/workspace && LOCK_WAIT_SECONDS=120 MAX_PARAREL_CRONTASKS_RUN=5 WATCHLIST_TICKERS='IREN'  HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=false HERMES_PERSISTENT_READY_WARMUP=false TIMEOUT_RETEST_ATTEMPTS=0 RUN_TIMEOUT_SECONDS=1500 DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true DIRECT_ALPACA_ONLY_MODE=false /home/me/git-repo/honey-barrel/workspace/scripts/daily_investment_watchlist_report_generator.sh --run-now >> /home/me/git-repo/honey-barrel/workspace/reports/.cron_state/cron_IREN.log 2>&1 # Daily Investment Watchlist Report Generator:IREN
 0,11,22,33,44,55 14-21 * * 1-5 cd /home/me/git-repo/honey-barrel/workspace && LOCK_WAIT_SECONDS=120 MAX_PARAREL_CRONTASKS_RUN=5 WATCHLIST_TICKERS='JOBY'  HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=false HERMES_PERSISTENT_READY_WARMUP=false TIMEOUT_RETEST_ATTEMPTS=0 RUN_TIMEOUT_SECONDS=1500 DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true DIRECT_ALPACA_ONLY_MODE=false /home/me/git-repo/honey-barrel/workspace/scripts/daily_investment_watchlist_report_generator.sh --run-now >> /home/me/git-repo/honey-barrel/workspace/reports/.cron_state/cron_JOBY.log 2>&1 # Daily Investment Watchlist Report Generator:JOBY
 1,12,23,34,45,56 14-21 * * 1-5 cd /home/me/git-repo/honey-barrel/workspace && LOCK_WAIT_SECONDS=120 MAX_PARAREL_CRONTASKS_RUN=5 WATCHLIST_TICKERS='KEEL'  HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=false HERMES_PERSISTENT_READY_WARMUP=false TIMEOUT_RETEST_ATTEMPTS=0 RUN_TIMEOUT_SECONDS=1500 DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true DIRECT_ALPACA_ONLY_MODE=false /home/me/git-repo/honey-barrel/workspace/scripts/daily_investment_watchlist_report_generator.sh --run-now >> /home/me/git-repo/honey-barrel/workspace/reports/.cron_state/cron_KEEL.log 2>&1 # Daily Investment Watchlist Report Generator:KEEL
 2,13,24,35,46,57 14-21 * * 1-5 cd /home/me/git-repo/honey-barrel/workspace && LOCK_WAIT_SECONDS=120 MAX_PARAREL_CRONTASKS_RUN=5 WATCHLIST_TICKERS='LITE'  HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=false HERMES_PERSISTENT_READY_WARMUP=false TIMEOUT_RETEST_ATTEMPTS=0 RUN_TIMEOUT_SECONDS=1500 DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true DIRECT_ALPACA_ONLY_MODE=false /home/me/git-repo/honey-barrel/workspace/scripts/daily_investment_watchlist_report_generator.sh --run-now >> /home/me/git-repo/honey-barrel/workspace/reports/.cron_state/cron_LITE.log 2>&1 # Daily Investment Watchlist Report Generator:LITE
 3,14,25,36,47,58 14-21 * * 1-5 cd /home/me/git-repo/honey-barrel/workspace && LOCK_WAIT_SECONDS=120 MAX_PARAREL_CRONTASKS_RUN=5 WATCHLIST_TICKERS='MARA'  HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=false HERMES_PERSISTENT_READY_WARMUP=false TIMEOUT_RETEST_ATTEMPTS=0 RUN_TIMEOUT_SECONDS=1500 DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true DIRECT_ALPACA_ONLY_MODE=false /home/me/git-repo/honey-barrel/workspace/scripts/daily_investment_watchlist_report_generator.sh --run-now >> /home/me/git-repo/honey-barrel/workspace/reports/.cron_state/cron_MARA.log 2>&1 # Daily Investment Watchlist Report Generator:MARA
 4,15,26,37,48,59 14-21 * * 1-5 cd /home/me/git-repo/honey-barrel/workspace && LOCK_WAIT_SECONDS=120 MAX_PARAREL_CRONTASKS_RUN=5 WATCHLIST_TICKERS='MRNA'  HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=false HERMES_PERSISTENT_READY_WARMUP=false TIMEOUT_RETEST_ATTEMPTS=0 RUN_TIMEOUT_SECONDS=1500 DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true DIRECT_ALPACA_ONLY_MODE=false /home/me/git-repo/honey-barrel/workspace/scripts/daily_investment_watchlist_report_generator.sh --run-now >> /home/me/git-repo/honey-barrel/workspace/reports/.cron_state/cron_MRNA.log 2>&1 # Daily Investment Watchlist Report Generator:MRNA
 5,16,27,38,49    14-21 * * 1-5 cd /home/me/git-repo/honey-barrel/workspace && LOCK_WAIT_SECONDS=120 MAX_PARAREL_CRONTASKS_RUN=5 WATCHLIST_TICKERS='MSFT'  HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=false HERMES_PERSISTENT_READY_WARMUP=false TIMEOUT_RETEST_ATTEMPTS=0 RUN_TIMEOUT_SECONDS=1500 DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true DIRECT_ALPACA_ONLY_MODE=false /home/me/git-repo/honey-barrel/workspace/scripts/daily_investment_watchlist_report_generator.sh --run-now >> /home/me/git-repo/honey-barrel/workspace/reports/.cron_state/cron_MSFT.log 2>&1 # Daily Investment Watchlist Report Generator:MSFT
 6,17,28,39,50    14-21 * * 1-5 cd /home/me/git-repo/honey-barrel/workspace && LOCK_WAIT_SECONDS=120 MAX_PARAREL_CRONTASKS_RUN=5 WATCHLIST_TICKERS='NVDA'  HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=false HERMES_PERSISTENT_READY_WARMUP=false TIMEOUT_RETEST_ATTEMPTS=0 RUN_TIMEOUT_SECONDS=1500 DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true DIRECT_ALPACA_ONLY_MODE=false /home/me/git-repo/honey-barrel/workspace/scripts/daily_investment_watchlist_report_generator.sh --run-now >> /home/me/git-repo/honey-barrel/workspace/reports/.cron_state/cron_NVDA.log 2>&1 # Daily Investment Watchlist Report Generator:NVDA
 7,18,29,40,51    14-21 * * 1-5 cd /home/me/git-repo/honey-barrel/workspace && LOCK_WAIT_SECONDS=120 MAX_PARAREL_CRONTASKS_RUN=5 WATCHLIST_TICKERS='ONDS'  HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=false HERMES_PERSISTENT_READY_WARMUP=false TIMEOUT_RETEST_ATTEMPTS=0 RUN_TIMEOUT_SECONDS=1500 DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true DIRECT_ALPACA_ONLY_MODE=false /home/me/git-repo/honey-barrel/workspace/scripts/daily_investment_watchlist_report_generator.sh --run-now >> /home/me/git-repo/honey-barrel/workspace/reports/.cron_state/cron_ONDS.log 2>&1 # Daily Investment Watchlist Report Generator:ONDS
 8,19,30,41,52    14-21 * * 1-5 cd /home/me/git-repo/honey-barrel/workspace && LOCK_WAIT_SECONDS=120 MAX_PARAREL_CRONTASKS_RUN=5 WATCHLIST_TICKERS='OPEN'  HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=false HERMES_PERSISTENT_READY_WARMUP=false TIMEOUT_RETEST_ATTEMPTS=0 RUN_TIMEOUT_SECONDS=1500 DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true DIRECT_ALPACA_ONLY_MODE=false /home/me/git-repo/honey-barrel/workspace/scripts/daily_investment_watchlist_report_generator.sh --run-now >> /home/me/git-repo/honey-barrel/workspace/reports/.cron_state/cron_OPEN.log 2>&1 # Daily Investment Watchlist Report Generator:OPEN
 9,20,31,42,53    14-21 * * 1-5 cd /home/me/git-repo/honey-barrel/workspace && LOCK_WAIT_SECONDS=120 MAX_PARAREL_CRONTASKS_RUN=5 WATCHLIST_TICKERS='PATH'  HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=false HERMES_PERSISTENT_READY_WARMUP=false TIMEOUT_RETEST_ATTEMPTS=0 RUN_TIMEOUT_SECONDS=1500 DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true DIRECT_ALPACA_ONLY_MODE=false /home/me/git-repo/honey-barrel/workspace/scripts/daily_investment_watchlist_report_generator.sh --run-now >> /home/me/git-repo/honey-barrel/workspace/reports/.cron_state/cron_PATH.log 2>&1 # Daily Investment Watchlist Report Generator:PATH
10,21,32,43,54    14-21 * * 1-5 cd /home/me/git-repo/honey-barrel/workspace && LOCK_WAIT_SECONDS=120 MAX_PARAREL_CRONTASKS_RUN=5 WATCHLIST_TICKERS='PLUG'  HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=false HERMES_PERSISTENT_READY_WARMUP=false TIMEOUT_RETEST_ATTEMPTS=0 RUN_TIMEOUT_SECONDS=1500 DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true DIRECT_ALPACA_ONLY_MODE=false /home/me/git-repo/honey-barrel/workspace/scripts/daily_investment_watchlist_report_generator.sh --run-now >> /home/me/git-repo/honey-barrel/workspace/reports/.cron_state/cron_PLUG.log 2>&1 # Daily Investment Watchlist Report Generator:PLUG
 0,11,22,33,44,55 14-21 * * 1-5 cd /home/me/git-repo/honey-barrel/workspace && LOCK_WAIT_SECONDS=120 MAX_PARAREL_CRONTASKS_RUN=5 WATCHLIST_TICKERS='PRDO'  HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=false HERMES_PERSISTENT_READY_WARMUP=false TIMEOUT_RETEST_ATTEMPTS=0 RUN_TIMEOUT_SECONDS=1500 DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true DIRECT_ALPACA_ONLY_MODE=false /home/me/git-repo/honey-barrel/workspace/scripts/daily_investment_watchlist_report_generator.sh --run-now >> /home/me/git-repo/honey-barrel/workspace/reports/.cron_state/cron_PRDO.log 2>&1 # Daily Investment Watchlist Report Generator:PRDO
 1,12,23,34,45,56 14-21 * * 1-5 cd /home/me/git-repo/honey-barrel/workspace && LOCK_WAIT_SECONDS=120 MAX_PARAREL_CRONTASKS_RUN=5 WATCHLIST_TICKERS='RIOT'  HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=false HERMES_PERSISTENT_READY_WARMUP=false TIMEOUT_RETEST_ATTEMPTS=0 RUN_TIMEOUT_SECONDS=1500 DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true DIRECT_ALPACA_ONLY_MODE=false /home/me/git-repo/honey-barrel/workspace/scripts/daily_investment_watchlist_report_generator.sh --run-now >> /home/me/git-repo/honey-barrel/workspace/reports/.cron_state/cron_RIOT.log 2>&1 # Daily Investment Watchlist Report Generator:RIOT
 2,13,24,35,46,57 14-21 * * 1-5 cd /home/me/git-repo/honey-barrel/workspace && LOCK_WAIT_SECONDS=120 MAX_PARAREL_CRONTASKS_RUN=5 WATCHLIST_TICKERS='RUN'   HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=false HERMES_PERSISTENT_READY_WARMUP=false TIMEOUT_RETEST_ATTEMPTS=0 RUN_TIMEOUT_SECONDS=1500 DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true DIRECT_ALPACA_ONLY_MODE=false /home/me/git-repo/honey-barrel/workspace/scripts/daily_investment_watchlist_report_generator.sh --run-now >> /home/me/git-repo/honey-barrel/workspace/reports/.cron_state/cron_RUN.log 2>&1 # Daily Investment Watchlist Report Generator:RUN
 3,14,25,36,47,58 14-21 * * 1-5 cd /home/me/git-repo/honey-barrel/workspace && LOCK_WAIT_SECONDS=120 MAX_PARAREL_CRONTASKS_RUN=5 WATCHLIST_TICKERS='SMCI'  HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=false HERMES_PERSISTENT_READY_WARMUP=false TIMEOUT_RETEST_ATTEMPTS=0 RUN_TIMEOUT_SECONDS=1500 DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true DIRECT_ALPACA_ONLY_MODE=false /home/me/git-repo/honey-barrel/workspace/scripts/daily_investment_watchlist_report_generator.sh --run-now >> /home/me/git-repo/honey-barrel/workspace/reports/.cron_state/cron_SMCI.log 2>&1 # Daily Investment Watchlist Report Generator:SMCI
 4,15,26,37,48,59 14-21 * * 1-5 cd /home/me/git-repo/honey-barrel/workspace && LOCK_WAIT_SECONDS=120 MAX_PARAREL_CRONTASKS_RUN=5 WATCHLIST_TICKERS='SNAP'  HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=false HERMES_PERSISTENT_READY_WARMUP=false TIMEOUT_RETEST_ATTEMPTS=0 RUN_TIMEOUT_SECONDS=1500 DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true DIRECT_ALPACA_ONLY_MODE=false /home/me/git-repo/honey-barrel/workspace/scripts/daily_investment_watchlist_report_generator.sh --run-now >> /home/me/git-repo/honey-barrel/workspace/reports/.cron_state/cron_SNAP.log 2>&1 # Daily Investment Watchlist Report Generator:SNAP
 5,16,27,38,49    14-21 * * 1-5 cd /home/me/git-repo/honey-barrel/workspace && LOCK_WAIT_SECONDS=120 MAX_PARAREL_CRONTASKS_RUN=5 WATCHLIST_TICKERS='SOFI'  HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=false HERMES_PERSISTENT_READY_WARMUP=false TIMEOUT_RETEST_ATTEMPTS=0 RUN_TIMEOUT_SECONDS=1500 DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true DIRECT_ALPACA_ONLY_MODE=false /home/me/git-repo/honey-barrel/workspace/scripts/daily_investment_watchlist_report_generator.sh --run-now >> /home/me/git-repo/honey-barrel/workspace/reports/.cron_state/cron_SOFI.log 2>&1 # Daily Investment Watchlist Report Generator:SOFI
 6,17,28,39,50    14-21 * * 1-5 cd /home/me/git-repo/honey-barrel/workspace && LOCK_WAIT_SECONDS=120 MAX_PARAREL_CRONTASKS_RUN=5 WATCHLIST_TICKERS='SOUN'  HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=false HERMES_PERSISTENT_READY_WARMUP=false TIMEOUT_RETEST_ATTEMPTS=0 RUN_TIMEOUT_SECONDS=1500 DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true DIRECT_ALPACA_ONLY_MODE=false /home/me/git-repo/honey-barrel/workspace/scripts/daily_investment_watchlist_report_generator.sh --run-now >> /home/me/git-repo/honey-barrel/workspace/reports/.cron_state/cron_SOUN.log 2>&1 # Daily Investment Watchlist Report Generator:SOUN
 7,18,29,40,51    14-21 * * 1-5 cd /home/me/git-repo/honey-barrel/workspace && LOCK_WAIT_SECONDS=120 MAX_PARAREL_CRONTASKS_RUN=5 WATCHLIST_TICKERS='TGTX'  HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=false HERMES_PERSISTENT_READY_WARMUP=false TIMEOUT_RETEST_ATTEMPTS=0 RUN_TIMEOUT_SECONDS=1500 DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true DIRECT_ALPACA_ONLY_MODE=false /home/me/git-repo/honey-barrel/workspace/scripts/daily_investment_watchlist_report_generator.sh --run-now >> /home/me/git-repo/honey-barrel/workspace/reports/.cron_state/cron_TGTX.log 2>&1 # Daily Investment Watchlist Report Generator:TGTX
 8,19,30,41,52    14-21 * * 1-5 cd /home/me/git-repo/honey-barrel/workspace && LOCK_WAIT_SECONDS=120 MAX_PARAREL_CRONTASKS_RUN=5 WATCHLIST_TICKERS='TSLA'  HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=false HERMES_PERSISTENT_READY_WARMUP=false TIMEOUT_RETEST_ATTEMPTS=0 RUN_TIMEOUT_SECONDS=1500 DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true DIRECT_ALPACA_ONLY_MODE=false /home/me/git-repo/honey-barrel/workspace/scripts/daily_investment_watchlist_report_generator.sh --run-now >> /home/me/git-repo/honey-barrel/workspace/reports/.cron_state/cron_TSLA.log 2>&1 # Daily Investment Watchlist Report Generator:TSLA
 9,20,31,42,53    14-21 * * 1-5 cd /home/me/git-repo/honey-barrel/workspace && LOCK_WAIT_SECONDS=120 MAX_PARAREL_CRONTASKS_RUN=5 WATCHLIST_TICKERS='UPST'  HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=false HERMES_PERSISTENT_READY_WARMUP=false TIMEOUT_RETEST_ATTEMPTS=0 RUN_TIMEOUT_SECONDS=1500 DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true DIRECT_ALPACA_ONLY_MODE=false /home/me/git-repo/honey-barrel/workspace/scripts/daily_investment_watchlist_report_generator.sh --run-now >> /home/me/git-repo/honey-barrel/workspace/reports/.cron_state/cron_UPST.log 2>&1 # Daily Investment Watchlist Report Generator:UPST
10,21,32,43,54    14-21 * * 1-5 cd /home/me/git-repo/honey-barrel/workspace && LOCK_WAIT_SECONDS=120 MAX_PARAREL_CRONTASKS_RUN=5 WATCHLIST_TICKERS='WULF'  HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=false HERMES_PERSISTENT_READY_WARMUP=false TIMEOUT_RETEST_ATTEMPTS=0 RUN_TIMEOUT_SECONDS=1500 DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true DIRECT_ALPACA_ONLY_MODE=false /home/me/git-repo/honey-barrel/workspace/scripts/daily_investment_watchlist_report_generator.sh --run-now >> /home/me/git-repo/honey-barrel/workspace/reports/.cron_state/cron_WULF.log 2>&1 # Daily Investment Watchlist Report Generator:WULF


*/45 * * * * cd /home/me/git-repo/honey-barrel/workspace && /home/me/git-repo/honey-barrel/workspace/scripts/hourly_watchlist_runtime_report.sh --run-now >> /home/me/git-repo/honey-barrel/workspace/reports/.cron_state/cron_hourly_watchlist_runtime.log 2>&1 # Hourly Watchlist Runtime Report

```

Copy file to `/home/me/git-repo/honey-barrel/workspace/backups/crontabs` and execute this:

```bash
crontab crontab_me_start.bak
```

You are Done! Welcome onboard.
