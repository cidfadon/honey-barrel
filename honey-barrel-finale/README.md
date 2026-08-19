Installation guide

1. Install ubuntu 24.04.4 LTS 
	a. while asked to create user , create user name -> me
	b. reboot and run update
2. install the following packages from App Center
	 Obsidian
	 Mousepad
3. Open firefox, download and install 
   Chrome
4. open chrome and login with your google account
	 Go to github and create your account if you dont have it or just login
5. open file explorer and in /home/me create new folder git-repo
6. open terminal and type 
```
   cd /home/me/git-repo
```
************************************************************
You can go to our page download and download it as zip to skip git installation. 
************************************************************

7. install git
```
sudo apt install git
```

9. generate your ssh key
```
ssh-keygen -t ed25519 -C "your_email_address@gmail.com"
```
10. now run this command
```
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/id_ed25519
cat ~/.ssh/id_ed25519.pub
```
From the output you will have last line starting with ssh-ed25519. Copy this line and go to your github page in chrome. Click top right at your profile -> settings -> SSH and GPG Keys. click on green button new SSH. Type Title it as you wish, leave Key type as Authentication Key and paste content of the line you copied before into Key field. Save it.

11. In github enter our repository

https://github.com/git-mb001/honey-barrel-lovable

a. click on Create new Fork. Leave default name
b. go to your profile and click on Repositories. you should see honey barrel there
c. click on honey-barrel repo and use green <> Code button
d. make sure you are on ssh tab, click on copy button

12. go back to terminal
make sure you are in /home/me/git-repo
paste it from your clipboard

```
git clone https://github.com/git-mb001/honey-barrel
```
hit enter you should see it downloading it

after its finished you should have honey-barrel folder in your git-repo

13. install curl
	```
	sudo apt install curl
	```

14.  install net-tools
	```
	    sudo apt install net-tools
	```

15. Install ollama
	```
	curl -fsSL https://ollama.com/install.sh | sh
	```
after ollama is installed run 
	```
	ollama list
	```
it will show you your models - we dont expect to see anything apart NAME, ID, SIZE, MODIFIED at this stage. 
	
Download ollama model, type:
```
ollama pull batiai/gemma4-e4b:q4
```
let it finish download.

Start ollama
```
ollama run batiai/gemma4-e4b:q4
```
15. install npm
```
sudo apt install npm
```

16. Install docker
```
 ls -ld /etc/apt/keyrings
```

if there is nothing in response type
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

make sure your ubuntu is using proper repo
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

now lets just fix perrmisions
```
sudo usermod -aG docker $USER

```

LOGOUT OF YOUR UBUNTU AND LOGIN AGAIN

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

At this point we should be done with installation all components

lets just create external volumes for docker
```
 docker volume create honey-barrel-stack_hermes_opt
 docker volume create honey-barrel-stack_hermes_data
```

we done with that part.
## Security

Go in terminal back to your git-repo and execute this:
```bash
export USER=me
export HOMEDIR=/home/me
export WORKSPACE=/home/me/git-repo/honey-barrel/workspace
```

then
```bash
mkdir -p $WORKSPACE
chown $USER:$USER -R $WORKSPACE $WORKSPACE/*
```

This step ensures that you have the appropriate permissions to access and modify files within your workspace.

now navigate to your workspace
```bash
cd /home/me/git-repo/honey-barrel/workspace
```


Create a `.env` file with the following entries:
```bash
OLLAMA_BASE_IP=your.local.ip.address
OLLAMA_BASE_URL=http://your.local.ip.address:11434
GITHUB_TOKEN=your_token_here
ALPACA_API_KEY_ID=your_key
ALPACA_API_SECRET_KEY=your_secret
```

Go and setup alpaca account and github account you will find your keys somewhere in security settings on those pages then update your .env file in any text editor.

## HB starting the stack

go to scripts
```
/git-repo/honey-barrel/workspace/scripts
```

type
```
./full_stack_recompose.sh 
```
 while ask you alway say yes.
as a result you should see something like that at the end.
```
[+] build 6/6
 ✔ Image honey-barrel-stack-alpaca-mcp             Built                                                                    101.7s
 ✔ Image honey-barrel-stack-investment-analyst-api Built                                                                    101.7s
 ✔ Image honey-barrel-stack-hermes                 Built                                                                    101.7s
 ✔ Image honey-barrel-stack-mcp-toolbox            Built                                                                    101.7s
 ✔ Image honey-barrel-stack-stdio-terminal         Built                                                                    101.7s
 ✔ Image honey-barrel-stack-workspace-mcp          Built                                                                    101.7s
Do you wish to recreate containers even if their configuration haven't changed? [Y/N] Y

Continue with "recreate" option..
[+] up 10/10
 ✔ Network honey-barrel-stack_backend-net  Created                                                                            0.0s
 ✔ Network honey-barrel-stack_frontend-net Created                                                                            0.0s
 ✔ Network honey-barrel-stack_mcp-net      Created                                                                            0.0s
 ✔ Container alpaca-mcp                    Started                                                                           18.3s
 ✔ Container workspace                     Started                                                                           18.3s
 ✔ Container investment-analyst-api        Started                                                                           18.3s
 ✔ Container workspace-mcp                 Started                                                                           18.4s
 ✔ Container stdio-terminal                Started                                                                           18.3s
 ✔ Container mcp-toolbox                   Started                                                                           15.6s
 ✔ Container hermes                        Started       
```

enter GUI
http://localhost:18001/ui/




now paste this and make sure you will answer as follows:
```
docker compose exec hermes hermes mcp add analyst --url http://investment-analyst-api:8001/mcp
docker compose exec hermes hermes mcp add workspace --url http://workspace-mcp:3001/mcp
docker compose exec hermes hermes mcp add alpaca --url http://alpaca-mcp:3001/mcp
docker compose exec hermes hermes mcp add terminal --url http://stdio-terminal:3002/mcp
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



In case you will have error related to dashboard from hermes

docker exec -it hermes sh -c "sed -i 's/host: 0.0.0.0/host: 127.0.0.1/' /opt/data/config.yaml"


Last step:

Enable crons

copy paste as a crontab_me_start.bak
```
CRON_TZ=Europe/Dublin

# --- AAPL ---
*/15 * * * * cd /home/me/git-repo/honey-barrel/workspace && LOCK_WAIT_SECONDS=120 MAX_PARAREL_CRONTASKS_RUN=2 WATCHLIST_TICKERS='AAPL' HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=false HERMES_PERSISTENT_READY_WARMUP=false TIMEOUT_RETEST_ATTEMPTS=0 RUN_TIMEOUT_SECONDS=1500 DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true DIRECT_ALPACA_ONLY_MODE=false /home/me/git-repo/honey-barrel/workspace/scripts/daily_investment_watchlist_report_generator.sh --run-now >> /home/me/git-repo/honey-barrel/workspace/reports/.cron_state/cron_AAPL.log 2>&1 # Daily Investment Watchlist Report Generator:AAPL
*/15 * * * * cd /home/me/git-repo/honey-barrel/workspace && LOCK_WAIT_SECONDS=120 MAX_PARAREL_CRONTASKS_RUN=2 WATCHLIST_TICKERS='AAPL' HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=false HERMES_PERSISTENT_READY_WARMUP=false TIMEOUT_RETEST_ATTEMPTS=0 RUN_TIMEOUT_SECONDS=1500 DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true DIRECT_ALPACA_ONLY_MODE=false /home/me/git-repo/honey-barrel/workspace/scripts/daily_investment_watchlist_report_generator.sh --run-now >> /home/me/git-repo/honey-barrel/workspace/reports/.cron_state/cron_AAPL.log 2>&1 # Daily Investment Watchlist Report Generator:AAPL

# --- GOOGL ---
*/15 * * * * cd /home/me/git-repo/honey-barrel/workspace && LOCK_WAIT_SECONDS=120 MAX_PARAREL_CRONTASKS_RUN=2 WATCHLIST_TICKERS='GOOGL' HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=false HERMES_PERSISTENT_READY_WARMUP=false TIMEOUT_RETEST_ATTEMPTS=0 RUN_TIMEOUT_SECONDS=1500 DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true DIRECT_ALPACA_ONLY_MODE=false /home/me/git-repo/honey-barrel/workspace/scripts/daily_investment_watchlist_report_generator.sh --run-now >> /home/me/git-repo/honey-barrel/workspace/reports/.cron_state/cron_GOOGL.log 2>&1 # Daily Investment Watchlist Report Generator:GOOGL
*/15 * * * * cd /home/me/git-repo/honey-barrel/workspace && LOCK_WAIT_SECONDS=120 MAX_PARAREL_CRONTASKS_RUN=2 WATCHLIST_TICKERS='GOOGL' HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=false HERMES_PERSISTENT_READY_WARMUP=false TIMEOUT_RETEST_ATTEMPTS=0 RUN_TIMEOUT_SECONDS=1500 DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true DIRECT_ALPACA_ONLY_MODE=false /home/me/git-repo/honey-barrel/workspace/scripts/daily_investment_watchlist_report_generator.sh --run-now >> /home/me/git-repo/honey-barrel/workspace/reports/.cron_state/cron_GOOGL.log 2>&1 # Daily Investment Watchlist Report Generator:GOOGL
*/15 * * * * cd /home/me/git-repo/honey-barrel/workspace && LOCK_WAIT_SECONDS=120 MAX_PARAREL_CRONTASKS_RUN=2 WATCHLIST_TICKERS='GOOGL' HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=false HERMES_PERSISTENT_READY_WARMUP=false TIMEOUT_RETEST_ATTEMPTS=0 RUN_TIMEOUT_SECONDS=1500 DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true DIRECT_ALPACA_ONLY_MODE=false /home/me/git-repo/honey-barrel/workspace/scripts/daily_investment_watchlist_report_generator.sh --run-now >> /home/me/git-repo/honey-barrel/workspace/reports/.cron_state/cron_GOOGL.log 2>&1 # Daily Investment Watchlist Report Generator:GOOGL

# --- AMZN ---
*/15 * * * * cd /home/me/git-repo/honey-barrel/workspace && LOCK_WAIT_SECONDS=120 MAX_PARAREL_CRONTASKS_RUN=2 WATCHLIST_TICKERS='AMZN' HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=false HERMES_PERSISTENT_READY_WARMUP=false TIMEOUT_RETEST_ATTEMPTS=0 RUN_TIMEOUT_SECONDS=1500 DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true DIRECT_ALPACA_ONLY_MODE=false /home/me/git-repo/honey-barrel/workspace/scripts/daily_investment_watchlist_report_generator.sh --run-now >> /home/me/git-repo/honey-barrel/workspace/reports/.cron_state/cron_AMZN.log 2>&1 # Daily Investment Watchlist Report Generator:AMZN
*/15 * * * * cd /home/me/git-repo/honey-barrel/workspace && LOCK_WAIT_SECONDS=120 MAX_PARAREL_CRONTASKS_RUN=2 WATCHLIST_TICKERS='AMZN' HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=false HERMES_PERSISTENT_READY_WARMUP=false TIMEOUT_RETEST_ATTEMPTS=0 RUN_TIMEOUT_SECONDS=1500 DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true DIRECT_ALPACA_ONLY_MODE=false /home/me/git-repo/honey-barrel/workspace/scripts/daily_investment_watchlist_report_generator.sh --run-now >> /home/me/git-repo/honey-barrel/workspace/reports/.cron_state/cron_AMZN.log 2>&1 # Daily Investment Watchlist Report Generator:AMZN
*/15 * * * * cd /home/me/git-repo/honey-barrel/workspace && LOCK_WAIT_SECONDS=120 MAX_PARAREL_CRONTASKS_RUN=2 WATCHLIST_TICKERS='AMZN' HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=false HERMES_PERSISTENT_READY_WARMUP=false TIMEOUT_RETEST_ATTEMPTS=0 RUN_TIMEOUT_SECONDS=1500 DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true DIRECT_ALPACA_ONLY_MODE=false /home/me/git-repo/honey-barrel/workspace/scripts/daily_investment_watchlist_report_generator.sh --run-now >> /home/me/git-repo/honey-barrel/workspace/reports/.cron_state/cron_AMZN.log 2>&1 # Daily Investment Watchlist Report Generator:AMZN

# --- NVDA ---
*/15 * * * * cd /home/me/git-repo/honey-barrel/workspace && LOCK_WAIT_SECONDS=120 MAX_PARAREL_CRONTASKS_RUN=2 WATCHLIST_TICKERS='NVDA' HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=false HERMES_PERSISTENT_READY_WARMUP=false TIMEOUT_RETEST_ATTEMPTS=0 RUN_TIMEOUT_SECONDS=1500 DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true DIRECT_ALPACA_ONLY_MODE=false /home/me/git-repo/honey-barrel/workspace/scripts/daily_investment_watchlist_report_generator.sh --run-now >> /home/me/git-repo/honey-barrel/workspace/reports/.cron_state/cron_NVDA.log 2>&1 # Daily Investment Watchlist Report Generator:NVDA
*/15 * * * * cd /home/me/git-repo/honey-barrel/workspace && LOCK_WAIT_SECONDS=120 MAX_PARAREL_CRONTASKS_RUN=2 WATCHLIST_TICKERS='NVDA' HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=false HERMES_PERSISTENT_READY_WARMUP=false TIMEOUT_RETEST_ATTEMPTS=0 RUN_TIMEOUT_SECONDS=1500 DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true DIRECT_ALPACA_ONLY_MODE=false /home/me/git-repo/honey-barrel/workspace/scripts/daily_investment_watchlist_report_generator.sh --run-now >> /home/me/git-repo/honey-barrel/workspace/reports/.cron_state/cron_NVDA.log 2>&1 # Daily Investment Watchlist Report Generator:NVDA
*/15 * * * * cd /home/me/git-repo/honey-barrel/workspace && LOCK_WAIT_SECONDS=120 MAX_PARAREL_CRONTASKS_RUN=2 WATCHLIST_TICKERS='NVDA' HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=false HERMES_PERSISTENT_READY_WARMUP=false TIMEOUT_RETEST_ATTEMPTS=0 RUN_TIMEOUT_SECONDS=1500 DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true DIRECT_ALPACA_ONLY_MODE=false /home/me/git-repo/honey-barrel/workspace/scripts/daily_investment_watchlist_report_generator.sh --run-now >> /home/me/git-repo/honey-barrel/workspace/reports/.cron_state/cron_NVDA.log 2>&1 # Daily Investment Watchlist Report Generator:NVDA

# --- MRVL ---
*/15 * * * * cd /home/me/git-repo/honey-barrel/workspace && LOCK_WAIT_SECONDS=120 MAX_PARAREL_CRONTASKS_RUN=2 WATCHLIST_TICKERS='MRVL' HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=false HERMES_PERSISTENT_READY_WARMUP=false TIMEOUT_RETEST_ATTEMPTS=0 RUN_TIMEOUT_SECONDS=1500 DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true DIRECT_ALPACA_ONLY_MODE=false /home/me/git-repo/honey-barrel/workspace/scripts/daily_investment_watchlist_report_generator.sh --run-now >> /home/me/git-repo/honey-barrel/workspace/reports/.cron_state/cron_MRVL.log 2>&1 # Daily Investment Watchlist Report Generator:MRVL
*/15 * * * * cd /home/me/git-repo/honey-barrel/workspace && LOCK_WAIT_SECONDS=120 MAX_PARAREL_CRONTASKS_RUN=2 WATCHLIST_TICKERS='MRVL' HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=false HERMES_PERSISTENT_READY_WARMUP=false TIMEOUT_RETEST_ATTEMPTS=0 RUN_TIMEOUT_SECONDS=1500 DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true DIRECT_ALPACA_ONLY_MODE=false /home/me/git-repo/honey-barrel/workspace/scripts/daily_investment_watchlist_report_generator.sh --run-now >> /home/me/git-repo/honey-barrel/workspace/reports/.cron_state/cron_MRVL.log 2>&1 # Daily Investment Watchlist Report Generator:MRVL
*/15 * * * * cd /home/me/git-repo/honey-barrel/workspace && LOCK_WAIT_SECONDS=120 MAX_PARAREL_CRONTASKS_RUN=2 WATCHLIST_TICKERS='MRVL' HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=false HERMES_PERSISTENT_READY_WARMUP=false TIMEOUT_RETEST_ATTEMPTS=0 RUN_TIMEOUT_SECONDS=1500 DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true DIRECT_ALPACA_ONLY_MODE=false /home/me/git-repo/honey-barrel/workspace/scripts/daily_investment_watchlist_report_generator.sh --run-now >> /home/me/git-repo/honey-barrel/workspace/reports/.cron_state/cron_MRVL.log 2>&1 # Daily Investment Watchlist Report Generator:MRVL

# --- SPCX ---
*/15 * * * * cd /home/me/git-repo/honey-barrel/workspace && LOCK_WAIT_SECONDS=120 MAX_PARAREL_CRONTASKS_RUN=2 WATCHLIST_TICKERS='SPCX' HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=false HERMES_PERSISTENT_READY_WARMUP=false TIMEOUT_RETEST_ATTEMPTS=0 RUN_TIMEOUT_SECONDS=1500 DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true DIRECT_ALPACA_ONLY_MODE=false /home/me/git-repo/honey-barrel/workspace/scripts/daily_investment_watchlist_report_generator.sh --run-now >> /home/me/git-repo/honey-barrel/workspace/reports/.cron_state/cron_SPCX.log 2>&1 # Daily Investment Watchlist Report Generator:SPCX
*/15 * * * * cd /home/me/git-repo/honey-barrel/workspace && LOCK_WAIT_SECONDS=120 MAX_PARAREL_CRONTASKS_RUN=2 WATCHLIST_TICKERS='SPCX' HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=false HERMES_PERSISTENT_READY_WARMUP=false TIMEOUT_RETEST_ATTEMPTS=0 RUN_TIMEOUT_SECONDS=1500 DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true DIRECT_ALPACA_ONLY_MODE=false /home/me/git-repo/honey-barrel/workspace/scripts/daily_investment_watchlist_report_generator.sh --run-now >> /home/me/git-repo/honey-barrel/workspace/reports/.cron_state/cron_SPCX.log 2>&1 # Daily Investment Watchlist Report Generator:SPCX
*/15 * * * * cd /home/me/git-repo/honey-barrel/workspace && LOCK_WAIT_SECONDS=120 MAX_PARAREL_CRONTASKS_RUN=2 WATCHLIST_TICKERS='SPCX' HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=false HERMES_PERSISTENT_READY_WARMUP=false TIMEOUT_RETEST_ATTEMPTS=0 RUN_TIMEOUT_SECONDS=1500 DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true DIRECT_ALPACA_ONLY_MODE=false /home/me/git-repo/honey-barrel/workspace/scripts/daily_investment_watchlist_report_generator.sh --run-now >> /home/me/git-repo/honey-barrel/workspace/reports/.cron_state/cron_SPCX.log 2>&1 # Daily Investment Watchlist Report Generator:SPCX

*/45 * * * * cd /home/me/git-repo/honey-barrel/workspace && /home/me/git-repo/honey-barrel/workspace/scripts/hourly_watchlist_runtime_report.sh --run-now >> /home/me/git-repo/honey-barrel/workspace/reports/.cron_state/cron_hourly_watchlist_runtime.log 2>&1 # Hourly Watchlist Runtime Report

```

copy file to :

/home/me/git-repo/honey-barrel/workspace/backups/crontabs

```
crontab crontab_me_start.bak 
```
