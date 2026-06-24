{
  description = "splunk — a small, scriptable CLI over the Splunk Enterprise REST API";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs =
    { self, nixpkgs }:
    let
      systems = [
        "x86_64-linux"
        "aarch64-linux"
        "x86_64-darwin"
        "aarch64-darwin"
      ];
      forAllSystems = f: nixpkgs.lib.genAttrs systems (system: f nixpkgs.legacyPackages.${system});
    in
    {
      devShells = forAllSystems (pkgs: {
        # Dev shell: Python plus uv and the lint/type tooling. The project itself is
        # installed with `uv pip install -e ".[dev]"` (see the shellHook), matching
        # the workflow documented in AGENTS.md and CI.
        default = pkgs.mkShell {
          packages = [
            pkgs.python313
            pkgs.uv
            pkgs.ruff
          ];
          shellHook = ''
            echo "vct-splunk-cli dev shell. First run:  uv venv && uv pip install -e \".[dev]\""
          '';
        };
      });
    };
}
