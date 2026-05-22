# --- GIDEON SYSTEM CONFIGURATION ---

# 1. Aliases (Your Shortcuts)
alias gideon='python ~/gideon.py'
alias cls='clear && figlet -f slant "G I D E O N" | lolcat'
alias update='pkg update && pkg upgrade'

# 2. Status Light Helper Function
check_net_status() {
    if ping -c 1 -W 1 8.8.8.8 > /dev/null 2>&1; then
        echo -e "\[\033[1;36m\]● ONLINE\[\033[0m\]"
    else
        echo -e "\[\033[1;31m\]○ OFFLINE\[\033[0m\]"
    fi
}

# 3. Dynamic Prompt Logic
set_gideon_prompt() {
    local NET_LIGHT=$(check_net_status)
    PS1="${NET_LIGHT} \[\033[1;37m\]Gideon-Terminal> \[\033[0m\]"
}

PROMPT_COMMAND=set_gideon_prompt

# 4. AUTO-START LOGIC
# This checks if Gideon is already running. If not, it launches him.
if ! pgrep -f "python ~/gideon.py" > /dev/null; then
    cls
    gideon
fi
