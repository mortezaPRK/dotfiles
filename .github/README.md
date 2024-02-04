# My Dotfiles :)

## Installation
1. `alias config='/usr/bin/git --git-dir=$HOME/.cfg/ --work-tree=$HOME'`
2. `git clone --bare git@github.com:mortezaPRK/dotfiles.git $HOME/.cfg`
3. `config checkout`
4. `config config --local status.showUntrackedFiles no`

Stolen from: https://www.atlassian.com/git/tutorials/dotfiles
