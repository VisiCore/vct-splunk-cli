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
        # Dev shell: Python plus ruff. Setup uses only `venv` and `pip` from the
        # standard library, so the commands here are the same ones in the README
        # and CI — a contributor without Nix runs exactly the same thing.
        default = pkgs.mkShell {
          packages = [
            pkgs.python314
            pkgs.ruff
            # Regenerates the hash-pinned CI locks; not needed to develop or
            # test. See the header of requirements-ci.in for the command.
            pkgs.uv
          ];
          shellHook = ''
            echo "vct-splunk-cli dev shell. First run:"
            echo "  python -m venv .venv && .venv/bin/python -m pip install -e \".[dev]\""
          '';
        };
      });
    };
}
