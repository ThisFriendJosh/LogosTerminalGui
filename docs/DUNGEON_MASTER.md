# Dungeon Master terminal

This terminal connects the real Dungeon World AI narrator and campaign engine through a separate Rust worker. It uses the same narrator instructions, read tools, validated responses, SQLite turns and engine dice as the desktop game. Models and game logic remain outside this GUI repository.

## Connect

The companion worker belongs to Dungeon World AI and is not bundled with this GUI. Use a backend build with its terminal-worker integration. Once the integration and build workflow are available upstream, prebuilt workers can be downloaded from **Actions > Build Dungeon Master terminal** there. Extract the artifact for your operating system, then choose that worker file in Settings. Linux users may need to restore executable permission with `chmod +x dwa-terminal`.

1. In a terminal-enabled [Dungeon World AI](https://github.com/ThisFriendJosh/Dungeon-World-AI) checkout, run `Build-Terminal-Connector.cmd` with the Rust toolchain installed. A checkout without this command still needs the companion integration. Select its `build/terminal/dwa-terminal.exe` output; the desktop GUI executable is a separate program. On Linux, use `cargo build --locked --release --manifest-path services/ai/Cargo.toml --bin dwa-terminal`.
2. In Logos Terminal GUI, select **Dungeon Master**, then **Settings > Terminal Manager > Settings**. Choose the worker file.
3. Existing Windows beta installations supply the default `llama-server.exe` and `Qwen3-4B-Q4_K_M.gguf`. Choose explicit existing files for a different installation. Blank/zero GPU layers uses CPU. The terminal does not install or download models.
4. Save settings, then **Test connection**. Open the workspace and choose **New campaign**, or send a **Play** action to create a default adventure. The model loads with the first action.

## Controls

| Action | Behavior |
|---|---|
| Play | Send the player's action to the existing DM engine |
| Campaigns / History | Choose and resume a saved terminal campaign |
| New campaign / New | Create a separate saved adventure, with an optional name |
| Characters | Blank lists characters; an exact name/ID selects one; `party` clears selection |
| Roll dice | Save an actual engine roll such as `1d20+3`, then reference the printed roll ID in Play |
| Status | Show model, campaign and prompt version |

Accepted turns save automatically. Reconnect restores the remembered campaign. Progress appears while the model loads, reads context and writes the reply. Stop/Disconnect stops the owned worker/model tree. The shared runtime retains its existing response timeout; no timeout adjustment is introduced by the connector.

Default saves are under `state/terminal-modules/dungeon-master/game-data/campaigns/`. The installed game's campaigns are not selected automatically. **Save root** can deliberately point to a folder containing an existing `campaigns` directory; back up that data and avoid concurrent play in the two interfaces. Initial tests should use the default separate folder.

This is a text testing interface. Tabletop/map editing, art and sheet editing remain in the Dungeon World app. The narrator does not apply mechanical changes, and a startup handshake does not certify inference or rule accuracy. These are the existing engine's boundaries.
