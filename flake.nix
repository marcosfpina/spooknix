# flake.nix
{
  description = "STT Pipeline - Privacy-first Speech-to-Text";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    sops-nix.url = "github:Mic92/sops-nix";
    sops-nix.inputs.nixpkgs.follows = "nixpkgs";
  };

  outputs =
    {
      self,
      nixpkgs,
      sops-nix,
    }:
    let
      system = "x86_64-linux";

      pkgs = import nixpkgs {
        inherit system;
        config = {
          allowUnfree = true;
          cudaSupport = true;
        };
      };

      # Python env com GTK4 bindings (nix, não pip)
      desktopPython = pkgs.python313.withPackages (ps: [
        ps.pygobject3
        ps.requests
        ps.numpy
      ]);

      # ── Wrappers ────────────────────────────────────────────────────────
      poetryWrappedCommand =
        name: command:
        pkgs.writeShellApplication {
          inherit name;
          runtimeInputs = [ pkgs.poetry ];
          text = ''
            exec poetry run ${command} "$@"
          '';
        };

      # Desktop: Poetry venv + Nix libs via PYTHONPATH sink
      spooknixDesktopCmd = pkgs.writeShellApplication {
        name = "spooknix-desktop";
        runtimeInputs = [
          desktopPython
        ];
        text = ''
          VENV_PYTHON="$PWD/.venv/bin/python"
          if [ ! -x "$VENV_PYTHON" ]; then
            echo "⚠️  .venv não encontrado. Rode 'nix develop' primeiro." >&2
            exit 1
          fi
          export PYTHONPATH="${desktopPython}/${desktopPython.sitePackages}:$PYTHONPATH"
          exec "$VENV_PYTHON" -m src.gui.app "$@"
        '';
      };

      spooknixCmd = poetryWrappedCommand "spooknix" "python -m src.cli";
      spooknixGuiCmd = poetryWrappedCommand "spooknix-gui" "python -m src.gui";
      pytestCmd = poetryWrappedCommand "pytest" "pytest";
      pytestCovCmd = pkgs.writeShellApplication {
        name = "pytest-cov";
        runtimeInputs = [ pkgs.poetry ];
        text = ''
          exec poetry run pytest --cov=src --cov-report=term-missing "$@"
        '';
      };

    in
    {
      # ── Dev shell ───────────────────────────────────────────────────────
      devShells.${system}.default = pkgs.mkShell {
        name = "stt-pipeline";

        nativeBuildInputs = with pkgs; [
          wrapGAppsHook4
          gobject-introspection
        ];

        packages = with pkgs; [
          # Python
          python313
          python313Packages.click
          python313Packages.pygobject3
          python313Packages.requests
          poetry

          # GTK4 system (typelibs via wrapGAppsHook4)
          gtk4
          libadwaita
          glib
          pango
          cairo
          gdk-pixbuf
          graphene
          harfbuzz

          spooknixCmd
          spooknixGuiCmd
          spooknixDesktopCmd
          pytestCmd
          pytestCovCmd

          # CUDA
          cudaPackages.cudatoolkit
          cudaPackages.cudnn

          # Áudio
          ffmpeg
          portaudio
          wl-clipboard

          # Signal processing
          blas
          lapack

          # Utils
          just

          # eBPF
          bpftrace
          bpfilter
          bpftools

          # Secrets
          sops
          age
        ];

        shellHook = ''
          echo ""
          echo "🎤 STT Pipeline - Ambiente de Desenvolvimento"
          echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
          echo ""

          if command -v nvidia-smi &> /dev/null; then
            echo "✅ GPU: $(nvidia-smi --query-gpu=name --format=csv,noheader)"
            echo "✅ VRAM: $(nvidia-smi --query-gpu=memory.total --format=csv,noheader)"
          else
            echo "⚠️  nvidia-smi não encontrado"
          fi
          echo ""

          if [ ! -d ".venv" ] || ! .venv/bin/python -c "import click" 2>/dev/null; then
            echo "📦 Instalando dependências com Poetry..."
            poetry install --with dev
          fi

          echo "🐍 Python: $(poetry run python --version)"
          echo "📁 Projeto: $(pwd)"
          echo ""
          echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
          echo "Core CLI:"
          echo "  spooknix info | doctor | record | stream | file"
          echo "  spooknix summarize | interview | brev"
          echo ""
          echo "Desktop (GTK4):"
          echo "  spooknix-desktop"
          echo ""
          echo "  pytest          → testes sem GPU/mic"
          echo "  pytest-cov      → com cobertura"
          echo ""

          export SOPS_AGE_KEY_FILE="$PWD/secrets/age.key"
          if [ -f "$SOPS_AGE_KEY_FILE" ] && [ -f "$PWD/secrets/secrets.yaml" ]; then
            export HF_TOKEN
            HF_TOKEN=$(sops -d --extract '["hf_token"]' "$PWD/secrets/secrets.yaml" 2>/dev/null || echo "")
            if [ -n "$HF_TOKEN" ]; then
              echo "🔑 Secrets: HF_TOKEN ✓ (via SOPS)"
            else
              echo "⚠️  Secrets: HF_TOKEN vazio"
            fi
            export OPENAI_API_KEY
            OPENAI_API_KEY=$(sops -d --extract '["openai_api_key"]' "$PWD/secrets/secrets.yaml" 2>/dev/null || echo "")
            if [ -n "$OPENAI_API_KEY" ]; then
              echo "🔑 Secrets: OPENAI_API_KEY ✓ (via SOPS)"
            elif [ -n "$LLM_BASE_URL" ]; then
              echo "🧠 LLM local: LLM_BASE_URL=$LLM_BASE_URL"
            else
              echo "ℹ️  LLM: defina LLM_BASE_URL ou OPENAI_API_KEY"
            fi
          else
            echo "⚠️  Secrets: secrets/age.key não encontrado"
          fi
          echo ""
        '';

        LD_LIBRARY_PATH = "${pkgs.stdenv.cc.cc.lib}/lib:${pkgs.cudaPackages.cudatoolkit}/lib:${pkgs.portaudio}/lib";
        HF_HOME = "$HOME/.cache/huggingface";
        HUGGINGFACE_HUB_CACHE = "$HOME/.cache/huggingface/hub";
        POETRY_VIRTUALENVS_IN_PROJECT = "true";
      };

      # ── Packages ────────────────────────────────────────────────────────
      packages.${system} = {
        default = spooknixDesktopCmd;
        spooknix-desktop = spooknixDesktopCmd;
      };

      # ── NixOS module ────────────────────────────────────────────────────
      nixosModules.default = import ./nix/modules/nixos/default.nix;
      nixosModules.spooknix = import ./nix/modules/nixos/default.nix;

      # ── Home-Manager module ─────────────────────────────────────────────
      homeManagerModules.default = import ./nix/modules/home-manager/default.nix;
      homeManagerModules.spooknix = import ./nix/modules/home-manager/default.nix;
    };
}
