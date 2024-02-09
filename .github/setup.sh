#!/bin/sh

set -e


# Allow non-interactive with sudo access
USER_NAME=$(whoami)
SUDOERS_FILE="/private/etc/sudoers.d/tbd"
sudo sh -c "echo '$USER_NAME ALL=(ALL) NOPASSWD: ALL' >> $SUDOERS_FILE"

# Install homebrew
export HOMEBREW_NO_ANALYTICS=1
NONINTERACTIVE=1 /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"


# configure dotfiles
alias config='/usr/bin/git --git-dir=$HOME/.cfg/ --work-tree=$HOME'
git clone --bare https://github.com/mortezaPRK/dotfiles.git $HOME/.cfg
config checkout
config config --local status.showUntrackedFiles no
config remote set-url origin git@github.com:mortezaPRK/dotfiles.git


# Install ohmyzsh
KEEP_ZSHRC=yes CHSH=no RUNZSH=no sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)"

# Generate ssh key
ssh-keygen -t ed25519 -q -f "$HOME/.ssh/id_ed25519" -N ""

# Packages
if [ -f "/usr/local/bin/brew" ]; then
    eval "$(/usr/local/bin/brew shellenv)"
elif [ -d "/opt/homebrew" ]; then
  eval "$(/opt/homebrew/bin/brew shellenv)"
fi

brew_taps="homebrew/cask-fonts github/gh "
brew_casks="rectangle visual-studio-code font-fira-code spotify vlc iterm2 "
brew_formula="asdf jq bash-completion watch gh "
if [ -n "$WORK_MACHINE" ] ; then
    brew_taps+="blendle/blendle "
    brew_casks+="datagrip postman docker intellij-idea slack "
    brew_formula+="jfrog-cli kns awscli kubernetes-cli libpq terraform grpcurl vault helm istioctl "
fi

for tap in $brew_taps; do
    brew tap $tap
done
brew install --cask $brew_casks
brew install $brew_formula

# Install other binaries
if [ -n "$WORK_MACHINE" ] ; then
    # KTX
    tmp_dir=$(mktemp -d)
    ktx_url=https://raw.githubusercontent.com/blendle/kns/master/bin/ktx

    curl $ktx_url -o $tmp_dir/ktx
    chmod +x $tmp_dir/ktx
    sudo mv $tmp_dir/ktx /usr/local/bin/ktx
    rm -rf $tmp_dir
    
    # Libpq
    brew link --force libpq
fi

# Remove passwordless sudo access
sudo rm -rf $SUDOERS_FILE

# System configs
defaults write com.apple.screencapture type jpg # JPG for screenshots
defaults write com.apple.dock persistent-apps -array # Reset the dock to empty
defaults write com.apple.finder ShowPathbar -bool true # show path bar
defaults write com.apple.finder ShowStatusBar -bool true # show status bar
defaults write NSGlobalDomain AppleShowAllExtensions -bool true # Finder: show all filename extensions
defaults write com.apple.finder FXEnableExtensionChangeWarning -bool false  # Disable the warning when changing a file extension
defaults write com.apple.desktopservices DSDontWriteNetworkStores -bool true # Avoid creating .DS_Store files on network volumes
defaults write com.apple.desktopservices DSDontWriteUSBStores -bool true # Avoid creating .DS_Store files on USB volumes
defaults write NSGlobalDomain ApplePressAndHoldEnabled -bool false # Disable press-and-hold for keys in favor of key repeat
defaults write -g InitialKeyRepeat -int 15 # Keyboard delay for repeat
defaults write -g KeyRepeat -int 2 # Keyboard repeat rate
defaults write com.apple.driver.AppleBluetoothMultitouch.trackpad Clicking -bool true # tap to click
defaults write com.apple.AppleMultitouchTrackpad Clicking -bool true  # tap to click

# Activate new settings
/System/Library/PrivateFrameworks/SystemAdministration.framework/Resources/activateSettings -u

# Kill to use new configs
killall Dock
killall Finder
