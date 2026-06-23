Make sure you have a locale which supports `UTF-8`.
If you are in a minimal environment (such as a Docker container), the locale may be something minimal like `POSIX`.
We test with the following settings. However, it should be fine if you are using a different UTF-8 supported locale.

```bash
locale  # check for UTF-8

sudo apt update && sudo apt install locales
sudo locale-gen en_US en_US.UTF-8
sudo update-locale LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8
export LANG=en_US.UTF-8

locale  # verify settings
```
