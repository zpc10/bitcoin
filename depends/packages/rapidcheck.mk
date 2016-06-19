package=rapidcheck

$(package)_version=1.0

$(package)_download_path=https://github.com/Christewart/rapidcheck/releases/download/1.0

$(package)_file_name=$(package)-$($(package)_version).tar.gz

$(package)_sha256_hash=c228dc21ec24618bfb6afa31d622d1f4ea71168f04ee499e1ffcfc63cd5833f4

define $(package)_preprocess_cmds
  mkdir build
endef

define $(package)_config_cmds
  cmake -DCMAKE_INSTALL_PREFIX:PATH=$(build_prefix)/bin ..
endef

define $(package)_build_cmds
  $(MAKE)
endef
