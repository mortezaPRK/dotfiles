export ZSH="$HOME/.oh-my-zsh"
export PATH="$HOME/.bin:$PATH"
export ASDF_DATA_DIR="$HOME/.asdf
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
ZSH_THEME="af-magic"  # bira
zstyle ':omz:update' mode disabled
COMPLETION_WAITING_DOTS="true"
DISABLE_UNTRACKED_FILES_DIRTY="true"
zstyle ':completion:*:*:docker:*' option-stacking yes
zstyle ':completion:*:*:docker-*:*' option-stacking yes

#######################################
############### PLUGINGS ##############
#######################################
plugins=(git asdf direnv docker)
fpath+=${ZSH}/custom/plugins/zsh-completions/src
autoload -U compinit && compinit
source $ZSH/oh-my-zsh.sh


# TODO: make it optional for work laptop
source <(stern --completion=zsh)
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

# Source local zshrc
[ -f $HOME/.local.zshrc ] && source $HOME/.local.zshrc
