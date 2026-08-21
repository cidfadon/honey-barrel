# Installation Guide

1. Install Ubuntu 24.04.4 LTS a. while asked to create user, create user name -> `me` b. reboot and run update
    
2. Install the following packages from App Center
    
    - Obsidian
    - Mousepad
3. Open Firefox, download and install Chrome
    
4. Open Chrome and login with your Google account
    
    - Go to GitHub and create your account if you don't have it, or just login
5. Open file explorer and in `/home/me` create new folder `git-repo`
    
6. Open terminal and type
    

```
cd /home/me/git-repo
```

## 7. GIT - you can skip it if you just want to download it and place it into folder

```
sudo apt install git
```

9. Generate your ssh key

```
ssh-keygen -t ed25519 -C "your_email_address@gmail.com"
```

10. Now run this command

```
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/id_ed25519
cat ~/.ssh/id_ed25519.pub
```

From the output you will have last line starting with `ssh-ed25519`. Copy this line and go to your GitHub page in Chrome. Click top right at your profile -> Settings -> SSH and GPG Keys. Click on the green button New SSH. Type Title as you wish, leave Key type as Authentication Key and paste content of the line you copied before into the Key field. Save it.

11. In GitHub enter our repository

[https://github.com/honeybarrelorg-collab/honey-barrel-finale](https://github.com/honeybarrelorg-collab/honey-barrel-finale)

a. click on Create new Fork. Leave default name b. go to your profile and click on Repositories. You should see honey barrel there c. click on honey-barrel repo and use green `<>` Code button d. make sure you are on the SSH tab, click on copy button

12. Go back to terminal, make sure you are in `/home/me/git-repo` and paste it from your clipboard

```
git clone git@github.com:honeybarrelorg-collab/honey-barrel-finale.git
```

Hit enter — you should see it downloading.

## Continue from here after skipping GIT config

Go to [https://github.com/honeybarrelorg-collab/honey-barrel-finale](https://github.com/honeybarrelorg-collab/honey-barrel-finale) and on the green button called "Code", download ZIP and extract it to `/home/me/git-repo/honey-barrel-finale`.

Done. Now let's open terminal and install all dependencies:

13. Install curl

```
sudo apt install curl
```

14. Install net-tools

```
sudo apt install net-tools
```

15. Install Ollama

```
curl -fsSL https://ollama.com/install.sh | sh
```

After Ollama is installed run

```
ollama list
```

It will show you your models — we don't expect to see anything apart from NAME, ID, SIZE, MODIFIED at this stage.

Download the Ollama model, type:

```
ollama pull batiai/gemma4-e4b:q4
```

Let it finish downloading.

Start Ollama

```
ollama run batiai/gemma4-e4b:q4
```

15. Install npm

```
sudo apt install npm
```

16. Install Docker

```
ls -ld /etc/apt/keyrings
```

If there is nothing in response, type

```
sudo mkdir -p /etc/apt/keyrings
sudo chmod 755 /etc/apt/keyrings
```

then

```
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
```

verify with

```
ls -l /etc/apt/keyrings/docker.asc
```

set permissions

```
sudo chmod a+r /etc/apt/keyrings/docker.asc
```

remove previous ones

```
sudo rm -f /etc/apt/sources.list.d/docker.list
```

make sure your Ubuntu is using proper repo

```
echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu noble stable" | sudo tee /etc/apt/sources.list.d/docker.list
```

update apt

```
sudo apt update
```

install docker

```
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

now let's just fix permissions

```
sudo usermod -aG docker $USER
```

**LOGOUT OF YOUR UBUNTU AND LOGIN AGAIN**

now paste this

```
docker ps
docker buildx ls
docker compose version
```

the results should be like:

```
CONTAINER ID   IMAGE     COMMAND   CREATED   STATUS    PORTS     NAMES
NAME/NODE     DRIVER/ENDPOINT   STATUS    BUILDKIT   PLATFORMS
default*      docker
 \_ default    \_ default       running   v0.31.2    linux/amd64 (+3)
Docker Compose version v5.3.1
```

At this point we should be done with installing all components.

Let's just create external volumes for Docker

```
docker volume create honey-barrel-stack_hermes_opt
docker volume create honey-barrel-stack_hermes_data
```

We're done with that part.

## Security

Go in terminal back to your git-repo and execute this:

```bash
export USER=me
export HOMEDIR=/home/me
export WORKSPACE=/home/me/git-repo/honey-barrel-finale/workspace
```

then

```bash
mkdir -p $WORKSPACE
chown $USER:$USER -R $WORKSPACE $WORKSPACE/*
```

This step ensures that you have the appropriate permissions to access and modify files within your workspace.

Now navigate to your workspace

```bash
cd /home/me/git-repo/honey-barrel-finale/workspace
```

Create a `.env` file with the following entries. You can find a template in `/honey-barrel-finale/.env.example` — edit this file, then change the name to `.env` and save it in your workspace and make a backup of it somewhere else.

TIP: if you don't see any `.env.example` in your file explorer, press Ctrl+H.

```bash
OLLAMA_BASE_IP=your.local.ip.address
OLLAMA_BASE_URL=http://your.local.ip.address:11434
GITHUB_TOKEN=your_token_here
ALPACA_API_KEY_ID=your_key
ALPACA_API_SECRET_KEY=your_secret
```

Your first step is to get your own IP address

```
ifconfig
```

You should get something like this in response

```
wlo1: flags=4163<UP,BROADCAST,RUNNING,MULTICAST>  mtu 1500
        inet 192.168.1.18  netmask 255.255.255.0  broadcast 192.168.1.255
        inet6 fe80::45a0:f42f:7c27:801a  prefixlen 64  scopeid 0x20<link>
        ether 60:67:20:a0:95:84  txqueuelen 1000  (Ethernet)
        RX packets 5569602  bytes 8346298843 (8.3 GB)
        RX errors 0  dropped 6106  overruns 0  frame 0
        TX packets 2178765  bytes 207867043 (207.8 MB)
        TX errors 0  dropped 0 overruns 0  carrier 0  collisions 0
```

Copy your.local.ip.address — in my case 192.168.1.18 — and paste it to the file.

Now for the Ollama model you have a standard one that we downloaded in the previous step (`OLLAMA_MODEL=batiai/gemma4-e4b:q4`). If you want to change the model just type:

```
ollama list
```

Expect a response like

```
NAME                    ID              SIZE      MODIFIED
batiai/gemma4-e4b:q4    d682bf87e3a3    5.3 GB    36 minutes ago
```

Copy and paste the name to the file.

## Register

Go and set up an Alpaca account and a GitHub account — you will find your keys somewhere in security settings on those pages — then update your `.env` file in any text editor.

## HB starting the stack

Go to scripts

```
cd /git-repo/honey-barrel-finale/workspace/scripts
```

type

```
./full_stack_recompose.sh
```

While asked, you always say yes. As a result you should see something like that at the end.

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

Enter GUI: [http://localhost:18001/ui/](http://localhost:18001/ui/)

Now paste this and make sure you will answer as follows:

```
docker compose exec hermes hermes mcp add analyst --url http://investment-analyst-api:8001/mcp
docker compose exec hermes hermes mcp add workspace --url http://workspace-mcp:3001/mcp
docker compose exec hermes hermes mcp add alpaca --url http://alpaca-mcp:3001/mcp
docker compose exec hermes hermes mcp add terminal --url http://stdio-terminal:3002/mcp
```

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

In case you will have an error related to the dashboard from Hermes:

```
docker exec -it hermes sh -c "sed -i 's/host: 0.0.0.0/host: 127.0.0.1/' /opt/data/config.yaml"
```

## Last step: Enable crons

Copy/paste as `crontab_me_start.bak`

```
CRON_TZ=Europe/Dublin

# --- AAPL ---
*/15 * * * * cd /home/me/git-repo/honey-barrel-finale/workspace && LOCK_WAIT_SECONDS=120 MAX_PARAREL_CRONTASKS_RUN=2 WATCHLIST_TICKERS='AAPL' HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=false HERMES_PERSISTENT_READY_WARMUP=false TIMEOUT_RETEST_ATTEMPTS=0 RUN_TIMEOUT_SECONDS=1500 DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true DIRECT_ALPACA_ONLY_MODE=false /home/me/git-repo/honey-barrel-finale/workspace/scripts/daily_investment_watchlist_report_generator.sh --run-now >> /home/me/git-repo/honey-barrel-finale/workspace/reports/.cron_state/cron_AAPL.log 2>&1 # Daily Investment Watchlist Report Generator:AAPL
*/15 * * * * cd /home/me/git-repo/honey-barrel-finale/workspace && LOCK_WAIT_SECONDS=120 MAX_PARAREL_CRONTASKS_RUN=2 WATCHLIST_TICKERS='AAPL' HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=false HERMES_PERSISTENT_READY_WARMUP=false TIMEOUT_RETEST_ATTEMPTS=0 RUN_TIMEOUT_SECONDS=1500 DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true DIRECT_ALPACA_ONLY_MODE=false /home/me/git-repo/honey-barrel-finale/workspace/scripts/daily_investment_watchlist_report_generator.sh --run-now >> /home/me/git-repo/honey-barrel-finale/workspace/reports/.cron_state/cron_AAPL.log 2>&1 # Daily Investment Watchlist Report Generator:AAPL

# --- GOOGL ---
*/15 * * * * cd /home/me/git-repo/honey-barrel-finale/workspace && LOCK_WAIT_SECONDS=120 MAX_PARAREL_CRONTASKS_RUN=2 WATCHLIST_TICKERS='GOOGL' HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=false HERMES_PERSISTENT_READY_WARMUP=false TIMEOUT_RETEST_ATTEMPTS=0 RUN_TIMEOUT_SECONDS=1500 DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true DIRECT_ALPACA_ONLY_MODE=false /home/me/git-repo/honey-barrel-finale/workspace/scripts/daily_investment_watchlist_report_generator.sh --run-now >> /home/me/git-repo/honey-barrel-finale/workspace/reports/.cron_state/cron_GOOGL.log 2>&1 # Daily Investment Watchlist Report Generator:GOOGL
*/15 * * * * cd /home/me/git-repo/honey-barrel-finale/workspace && LOCK_WAIT_SECONDS=120 MAX_PARAREL_CRONTASKS_RUN=2 WATCHLIST_TICKERS='GOOGL' HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=false HERMES_PERSISTENT_READY_WARMUP=false TIMEOUT_RETEST_ATTEMPTS=0 RUN_TIMEOUT_SECONDS=1500 DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true DIRECT_ALPACA_ONLY_MODE=false /home/me/git-repo/honey-barrel-finale/workspace/scripts/daily_investment_watchlist_report_generator.sh --run-now >> /home/me/git-repo/honey-barrel-finale/workspace/reports/.cron_state/cron_GOOGL.log 2>&1 # Daily Investment Watchlist Report Generator:GOOGL
*/15 * * * * cd /home/me/git-repo/honey-barrel-finale/workspace && LOCK_WAIT_SECONDS=120 MAX_PARAREL_CRONTASKS_RUN=2 WATCHLIST_TICKERS='GOOGL' HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=false HERMES_PERSISTENT_READY_WARMUP=false TIMEOUT_RETEST_ATTEMPTS=0 RUN_TIMEOUT_SECONDS=1500 DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true DIRECT_ALPACA_ONLY_MODE=false /home/me/git-repo/honey-barrel-finale/workspace/scripts/daily_investment_watchlist_report_generator.sh --run-now >> /home/me/git-repo/honey-barrel-finale/workspace/reports/.cron_state/cron_GOOGL.log 2>&1 # Daily Investment Watchlist Report Generator:GOOGL

# --- AMZN ---
*/15 * * * * cd /home/me/git-repo/honey-barrel-finale/workspace && LOCK_WAIT_SECONDS=120 MAX_PARAREL_CRONTASKS_RUN=2 WATCHLIST_TICKERS='AMZN' HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=false HERMES_PERSISTENT_READY_WARMUP=false TIMEOUT_RETEST_ATTEMPTS=0 RUN_TIMEOUT_SECONDS=1500 DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true DIRECT_ALPACA_ONLY_MODE=false /home/me/git-repo/honey-barrel-finale/workspace/scripts/daily_investment_watchlist_report_generator.sh --run-now >> /home/me/git-repo/honey-barrel-finale/workspace/reports/.cron_state/cron_AMZN.log 2>&1 # Daily Investment Watchlist Report Generator:AMZN
*/15 * * * * cd /home/me/git-repo/honey-barrel-finale/workspace && LOCK_WAIT_SECONDS=120 MAX_PARAREL_CRONTASKS_RUN=2 WATCHLIST_TICKERS='AMZN' HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=false HERMES_PERSISTENT_READY_WARMUP=false TIMEOUT_RETEST_ATTEMPTS=0 RUN_TIMEOUT_SECONDS=1500 DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true DIRECT_ALPACA_ONLY_MODE=false /home/me/git-repo/honey-barrel-finale/workspace/scripts/daily_investment_watchlist_report_generator.sh --run-now >> /home/me/git-repo/honey-barrel-finale/workspace/reports/.cron_state/cron_AMZN.log 2>&1 # Daily Investment Watchlist Report Generator:AMZN
*/15 * * * * cd /home/me/git-repo/honey-barrel-finale/workspace && LOCK_WAIT_SECONDS=120 MAX_PARAREL_CRONTASKS_RUN=2 WATCHLIST_TICKERS='AMZN' HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=false HERMES_PERSISTENT_READY_WARMUP=false TIMEOUT_RETEST_ATTEMPTS=0 RUN_TIMEOUT_SECONDS=1500 DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true DIRECT_ALPACA_ONLY_MODE=false /home/me/git-repo/honey-barrel-finale/workspace/scripts/daily_investment_watchlist_report_generator.sh --run-now >> /home/me/git-repo/honey-barrel-finale/workspace/reports/.cron_state/cron_AMZN.log 2>&1 # Daily Investment Watchlist Report Generator:AMZN

# --- NVDA ---
*/15 * * * * cd /home/me/git-repo/honey-barrel-finale/workspace && LOCK_WAIT_SECONDS=120 MAX_PARAREL_CRONTASKS_RUN=2 WATCHLIST_TICKERS='NVDA' HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=false HERMES_PERSISTENT_READY_WARMUP=false TIMEOUT_RETEST_ATTEMPTS=0 RUN_TIMEOUT_SECONDS=1500 DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true DIRECT_ALPACA_ONLY_MODE=false /home/me/git-repo/honey-barrel-finale/workspace/scripts/daily_investment_watchlist_report_generator.sh --run-now >> /home/me/git-repo/honey-barrel-finale/workspace/reports/.cron_state/cron_NVDA.log 2>&1 # Daily Investment Watchlist Report Generator:NVDA
*/15 * * * * cd /home/me/git-repo/honey-barrel-finale/workspace && LOCK_WAIT_SECONDS=120 MAX_PARAREL_CRONTASKS_RUN=2 WATCHLIST_TICKERS='NVDA' HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=false HERMES_PERSISTENT_READY_WARMUP=false TIMEOUT_RETEST_ATTEMPTS=0 RUN_TIMEOUT_SECONDS=1500 DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true DIRECT_ALPACA_ONLY_MODE=false /home/me/git-repo/honey-barrel-finale/workspace/scripts/daily_investment_watchlist_report_generator.sh --run-now >> /home/me/git-repo/honey-barrel-finale/workspace/reports/.cron_state/cron_NVDA.log 2>&1 # Daily Investment Watchlist Report Generator:NVDA
*/15 * * * * cd /home/me/git-repo/honey-barrel-finale/workspace && LOCK_WAIT_SECONDS=120 MAX_PARAREL_CRONTASKS_RUN=2 WATCHLIST_TICKERS='NVDA' HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=false HERMES_PERSISTENT_READY_WARMUP=false TIMEOUT_RETEST_ATTEMPTS=0 RUN_TIMEOUT_SECONDS=1500 DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true DIRECT_ALPACA_ONLY_MODE=false /home/me/git-repo/honey-barrel-finale/workspace/scripts/daily_investment_watchlist_report_generator.sh --run-now >> /home/me/git-repo/honey-barrel-finale/workspace/reports/.cron_state/cron_NVDA.log 2>&1 # Daily Investment Watchlist Report Generator:NVDA

# --- MRVL ---
*/15 * * * * cd /home/me/git-repo/honey-barrel-finale/workspace && LOCK_WAIT_SECONDS=120 MAX_PARAREL_CRONTASKS_RUN=2 WATCHLIST_TICKERS='MRVL' HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=false HERMES_PERSISTENT_READY_WARMUP=false TIMEOUT_RETEST_ATTEMPTS=0 RUN_TIMEOUT_SECONDS=1500 DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true DIRECT_ALPACA_ONLY_MODE=false /home/me/git-repo/honey-barrel-finale/workspace/scripts/daily_investment_watchlist_report_generator.sh --run-now >> /home/me/git-repo/honey-barrel-finale/workspace/reports/.cron_state/cron_MRVL.log 2>&1 # Daily Investment Watchlist Report Generator:MRVL
*/15 * * * * cd /home/me/git-repo/honey-barrel-finale/workspace && LOCK_WAIT_SECONDS=120 MAX_PARAREL_CRONTASKS_RUN=2 WATCHLIST_TICKERS='MRVL' HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=false HERMES_PERSISTENT_READY_WARMUP=false TIMEOUT_RETEST_ATTEMPTS=0 RUN_TIMEOUT_SECONDS=1500 DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true DIRECT_ALPACA_ONLY_MODE=false /home/me/git-repo/honey-barrel-finale/workspace/scripts/daily_investment_watchlist_report_generator.sh --run-now >> /home/me/git-repo/honey-barrel-finale/workspace/reports/.cron_state/cron_MRVL.log 2>&1 # Daily Investment Watchlist Report Generator:MRVL
*/15 * * * * cd /home/me/git-repo/honey-barrel-finale/workspace && LOCK_WAIT_SECONDS=120 MAX_PARAREL_CRONTASKS_RUN=2 WATCHLIST_TICKERS='MRVL' HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=false HERMES_PERSISTENT_READY_WARMUP=false TIMEOUT_RETEST_ATTEMPTS=0 RUN_TIMEOUT_SECONDS=1500 DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true DIRECT_ALPACA_ONLY_MODE=false /home/me/git-repo/honey-barrel-finale/workspace/scripts/daily_investment_watchlist_report_generator.sh --run-now >> /home/me/git-repo/honey-barrel-finale/workspace/reports/.cron_state/cron_MRVL.log 2>&1 # Daily Investment Watchlist Report Generator:MRVL

# --- SPCX ---
*/15 * * * * cd /home/me/git-repo/honey-barrel-finale/workspace && LOCK_WAIT_SECONDS=120 MAX_PARAREL_CRONTASKS_RUN=2 WATCHLIST_TICKERS='SPCX' HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=false HERMES_PERSISTENT_READY_WARMUP=false TIMEOUT_RETEST_ATTEMPTS=0 RUN_TIMEOUT_SECONDS=1500 DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true DIRECT_ALPACA_ONLY_MODE=false /home/me/git-repo/honey-barrel-finale/workspace/scripts/daily_investment_watchlist_report_generator.sh --run-now >> /home/me/git-repo/honey-barrel-finale/workspace/reports/.cron_state/cron_SPCX.log 2>&1 # Daily Investment Watchlist Report Generator:SPCX
*/15 * * * * cd /home/me/git-repo/honey-barrel-finale/workspace && LOCK_WAIT_SECONDS=120 MAX_PARAREL_CRONTASKS_RUN=2 WATCHLIST_TICKERS='SPCX' HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=false HERMES_PERSISTENT_READY_WARMUP=false TIMEOUT_RETEST_ATTEMPTS=0 RUN_TIMEOUT_SECONDS=1500 DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true DIRECT_ALPACA_ONLY_MODE=false /home/me/git-repo/honey-barrel-finale/workspace/scripts/daily_investment_watchlist_report_generator.sh --run-now >> /home/me/git-repo/honey-barrel-finale/workspace/reports/.cron_state/cron_SPCX.log 2>&1 # Daily Investment Watchlist Report Generator:SPCX
*/15 * * * * cd /home/me/git-repo/honey-barrel-finale/workspace && LOCK_WAIT_SECONDS=120 MAX_PARAREL_CRONTASKS_RUN=2 WATCHLIST_TICKERS='SPCX' HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=false HERMES_PERSISTENT_READY_WARMUP=false TIMEOUT_RETEST_ATTEMPTS=0 RUN_TIMEOUT_SECONDS=1500 DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true DIRECT_ALPACA_ONLY_MODE=false /home/me/git-repo/honey-barrel-finale/workspace/scripts/daily_investment_watchlist_report_generator.sh --run-now >> /home/me/git-repo/honey-barrel-finale/workspace/reports/.cron_state/cron_SPCX.log 2>&1 # Daily Investment Watchlist Report Generator:SPCX

*/45 * * * * cd /home/me/git-repo/honey-barrel-finale/workspace && /home/me/git-repo/honey-barrel-finale/workspace/scripts/hourly_watchlist_runtime_report.sh --run-now >> /home/me/git-repo/honey-barrel-finale/workspace/reports/.cron_state/cron_hourly_watchlist_runtime.log 2>&1 # Hourly Watchlist Runtime Report
```

Copy file to:

`/home/me/git-repo/honey-barrel-finale/workspace/backups/crontabs`

Go in terminal to this folder and execute:

```
crontab crontab_me_start.bak
```

You are Done! Welcome onboard.
