export PATH="$HOME/.bin:$HOME/.local/bin:$PATH"
export ASDF_DATA_DIR="$HOME/.asdf"
export PATH="$ASDF_DATA_DIR/shims:$PATH"

#######################################
########### HISTORY CONFIGS ###########
#######################################
HISTSIZE=10000
SAVEHIST=10000
HISTFILE=$HOME/.zsh_history
HISTORY_IGNORE="(ls *|cd *|pwd|exit|date *|* --help|ll *|lla *)"
setopt histignorealldups sharehistory
setopt appendhistory
setopt hist_ignore_dups
setopt hist_ignore_space

#######################################
############ ZSH CONFIGS ##############
#######################################
bindkey '^R' history-incremental-search-backward
autoload -U up-line-or-beginning-search
autoload -U down-line-or-beginning-search
zle -N up-line-or-beginning-search
zle -N down-line-or-beginning-search
bindkey "^[[A" up-line-or-beginning-search   # Up arrow
bindkey "^[[B" down-line-or-beginning-search # Down arrow

#######################################
############### PLUGINGS ##############
#######################################
fpath+=${ZSH}/custom/plugins/zsh-completions/src
fpath=(${ASDF_DATA_DIR:-$HOME/.asdf}/completions $fpath)
autoload -U compinit && compinit

[[ -f ${ASDF_DATA_DIR}/plugins/java/set-java-home.zsh ]] && . ${ASDF_DATA_DIR}/plugins/java/set-java-home.zsh
command -v stern &> /dev/null && source <(stern --completion=zsh)
#######################################
################ COMMON ###############
#######################################
export LANG=en_US.UTF-8
export PYTHONSTARTUP=$HOME/.pythonrc

#######################################
############## ALIASES ################
#######################################
alias config='/usr/bin/git --git-dir=$HOME/.cfg/ --work-tree=$HOME'
alias k='kubectl'
alias d='docker'
alias dc='docker compose'
alias cdtmp='cd `mktemp -d`'

#######################################
############## FUNCTIONS ##############
#######################################
function clone () {
    clone_path=$(echo $1 | sed -e 's/^git:\/\///' -e 's/^https\?:\/\///' -e 's/:/\//g' -e 's/\.git$//' -e 's/^git@//')
    clone_path="$HOME/Work/${clone_path}"
    mkdir -p $clone_path
    git clone $1 $clone_path
    cd $clone_path
}

claudew() {
    local config_file="$HOME/.config/claudew.json"
    local mode="${CLAUDEW_MODE}"

    # Check if config file exists
    if [[ ! -f "$config_file" ]]; then
        echo "Error: Config file not found at $config_file" >&2
        return 1
    fi

    if ! command -v fzf &> /dev/null; then
        echo "Error: fzf is not installed." >&2
        return 1
    fi

    if ! command -v jq &> /dev/null; then
        echo "Error: jq is not installed." >&2
        return 1
    fi

    # If mode not set via env, check for fzf and prompt
    while ! jq -e --arg mode "$mode" '.[$mode]' "$config_file" &> /dev/null; do
        mode=$(jq -r 'keys[]' "$config_file" | fzf --prompt="Select Claude environment: " --height=40% --reverse)

        if [[ -z "$mode" ]]; then
            echo "No environment selected, please try again" >&2
        elif ! jq -e --arg mode "$mode" '.[$mode]' "$config_file" &> /dev/null; then
            echo "Mode '$mode' not found in config, please select again" >&2
            mode=""
        fi
    done

      (                                                                                                                                                                                                     
          while IFS='=' read -r key value; do                                                                                                                                                               
              export "$key=$value"                                                                                                                                                                          
          done < <(jq -r --arg mode "$mode" '.[$mode] | to_entries | .[] | "\(.key)=\(.value)"' "$config_file")                                                                                             
          claude "$@"                                                                                                                                                                                       
      )  
}

function cleanupClaudeJson () {
    jq '.projects |= with_entries(select(.key | startswith("/private/var/folders/") | not))' ~/.claude.json > tmp.json
    mv tmp.json ~/.claude.json
}

# Source local zshrc
[ -f $HOME/.local.zshrc ] && source $HOME/.local.zshrc

export PATH="/usr/local/opt/ruby/bin:$PATH"
export GEM_HOME=$HOME/.gem
export PATH="$GEM_HOME/ruby/4.0.0/bin:$GEM_HOME/bin:$PATH"
eval "$(starship init zsh)"
