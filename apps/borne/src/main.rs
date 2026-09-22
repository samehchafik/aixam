//! borne.exe : une page web en plein ecran, sans bord, toujours au premier
//! plan, sur l'ecran choisi. Alt+F4 ferme -- c'est la sortie de secours, et
//! elle reste volontairement celle de Windows.
//!
//!   borne.exe http://localhost:8080/kiosk/
//!   borne.exe http://localhost:8080/kiosk/#/display --ecran 1
//!   borne.exe http://localhost:8080/kiosk/ --ecran principal --titre "AIXAM tactile"
//!   borne.exe http://localhost:8080/kiosk/ --ecran 3840,0
//!
//! Pourquoi un executable a nous plutot que Chrome en mode kiosque : Chrome
//! n'a aucune option pour le premier plan, ignore --window-position sous
//! Windows quand il est en --kiosk, et refait sa fenetre en passant en plein
//! ecran -- d'ou un script qui le pose apres coup et un veilleur qui
//! reaffirme l'attribut chaque seconde. Ici la fenetre est la notre : on la
//! pose sur le moniteur voulu, on la remet en place si Windows recompose le
//! bureau (capot d'un portable, cable rebranche), et on reprend le focus
//! quand quelque chose l'a pris -- sauf le clavier tactile, tant qu'il est
//! ouvert, sinon il se refermerait sous les doigts du visiteur.
//!
//! Le moteur est le WebView2 de Windows : le meme que Chrome/Edge, deja sur
//! la machine.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::time::Duration;
use tauri::{
    Manager, Monitor, PhysicalPosition, PhysicalSize, WebviewUrl, WebviewWindow,
    WebviewWindowBuilder, WindowEvent,
};

const USAGE: &str = "usage : borne.exe <url> [--ecran principal|N|x,y] [--titre <titre>]

  <url>            la page a ouvrir (http:// ou https://)
  --ecran          principal (defaut), le numero d'un moniteur (0, 1, ...), ou
                   la position x,y d'un moniteur telle que Windows la donne
  --titre          le titre de la fenetre (invisible, mais utile dans un journal)

Alt+F4 ferme la fenetre et termine le programme.";

/// Sur quel moniteur poser la fenetre.
#[derive(Clone, Debug)]
enum Ecran {
    Principal,
    Numero(usize),
    /// La position d'un moniteur dans le bureau. C'est ce que releve le
    /// back-office, et ca survit a un moniteur renumerote.
    Position(i32, i32),
}

struct Options {
    url: String,
    ecran: Ecran,
    titre: String,
}

fn lire_options() -> Result<Options, String> {
    let mut args = std::env::args().skip(1);
    let mut url = None;
    let mut ecran = Ecran::Principal;
    let mut titre = String::from("AIXAM");
    while let Some(a) = args.next() {
        match a.as_str() {
            "--ecran" => {
                let v = args.next().ok_or("--ecran attend une valeur")?;
                ecran = analyser_ecran(&v)?;
            }
            "--titre" => titre = args.next().ok_or("--titre attend une valeur")?,
            "-h" | "--help" | "/?" => return Err(String::new()),
            _ if a.starts_with('-') => return Err(format!("option inconnue : {a}")),
            _ => {
                if url.is_some() {
                    return Err(format!("une seule url a la fois : {a} est en trop"));
                }
                url = Some(a);
            }
        }
    }
    let url = url.ok_or("l'url de la page a ouvrir manque")?;
    if !(url.starts_with("http://") || url.starts_with("https://")) {
        return Err(format!("url invalide, il faut http:// ou https:// : {url}"));
    }
    Ok(Options { url, ecran, titre })
}

fn analyser_ecran(v: &str) -> Result<Ecran, String> {
    if v.eq_ignore_ascii_case("principal") {
        return Ok(Ecran::Principal);
    }
    if let Ok(n) = v.parse::<usize>() {
        return Ok(Ecran::Numero(n));
    }
    if let Some((x, y)) = v.split_once(',') {
        if let (Ok(x), Ok(y)) = (x.trim().parse::<i32>(), y.trim().parse::<i32>()) {
            return Ok(Ecran::Position(x, y));
        }
    }
    Err(format!("--ecran : attendu principal, un numero ou x,y ; recu {v}"))
}

fn contient(m: &Monitor, x: i32, y: i32) -> bool {
    let (p, s) = (m.position(), m.size());
    x >= p.x && y >= p.y && x < p.x + s.width as i32 && y < p.y + s.height as i32
}

/// Le moniteur demande, ou le plus proche de ce qui a ete demande : un numero
/// trop grand prend le dernier, une position qui n'est plus au coin d'un ecran
/// prend celui qui la contient, et sinon l'ecran principal -- mais jamais rien.
fn choisir_moniteur(app: &tauri::AppHandle, ecran: &Ecran) -> Option<Monitor> {
    let tous = app.available_monitors().ok()?;
    let principal = || app.primary_monitor().ok().flatten().or_else(|| tous.first().cloned());
    match ecran {
        Ecran::Principal => principal(),
        Ecran::Numero(n) => tous.get(*n).cloned().or_else(|| tous.last().cloned()),
        Ecran::Position(x, y) => tous
            .iter()
            .find(|m| m.position().x == *x && m.position().y == *y)
            .or_else(|| tous.iter().find(|m| contient(m, *x, *y)))
            .cloned()
            .or_else(principal),
    }
}

fn rect(m: &Monitor) -> (i32, i32, u32, u32) {
    (m.position().x, m.position().y, m.size().width, m.size().height)
}

/// Pose la fenetre sur le moniteur : hors plein ecran d'abord, sinon la
/// position est ignoree, puis plein ecran sur place, premier plan, focus.
fn poser(fenetre: &WebviewWindow, m: &Monitor) {
    let _ = fenetre.set_fullscreen(false);
    let _ = fenetre.set_position(PhysicalPosition::new(m.position().x, m.position().y));
    let _ = fenetre.set_size(PhysicalSize::new(m.size().width, m.size().height));
    let _ = fenetre.set_fullscreen(true);
    let _ = fenetre.set_always_on_top(true);
    let _ = fenetre.set_focus();
}

/// Ce que la page ne doit pas offrir sur un stand : le menu contextuel (qui
/// donne acces a « Inspecter »), et le zoom au pincement.
const GARDE_FOUS: &str = r#"
document.addEventListener('contextmenu', e => e.preventDefault(), true);
document.addEventListener('gesturestart', e => e.preventDefault(), true);
"#;

/// Le clavier tactile de Windows a-t-il le premier plan ? TabTip (Windows 10)
/// a sa classe ; sous Windows 11 c'est une CoreWindow de TextInputHost.
#[cfg(windows)]
fn clavier_tactile_devant() -> bool {
    use windows_sys::Win32::UI::WindowsAndMessaging::{GetClassNameW, GetForegroundWindow, GetWindowTextW};
    unsafe {
        let h = GetForegroundWindow();
        if h.is_null() {
            return false;
        }
        let mut tampon = [0u16; 128];
        let n = GetClassNameW(h, tampon.as_mut_ptr(), tampon.len() as i32);
        let classe = String::from_utf16_lossy(&tampon[..n.max(0) as usize]);
        if classe == "IPTip_Main_Window" {
            return true;
        }
        if classe == "Windows.UI.Core.CoreWindow" {
            let n = GetWindowTextW(h, tampon.as_mut_ptr(), tampon.len() as i32);
            let titre = String::from_utf16_lossy(&tampon[..n.max(0) as usize]).to_lowercase();
            return titre.contains("text input") || titre.contains("clavier");
        }
        false
    }
}

#[cfg(not(windows))]
fn clavier_tactile_devant() -> bool {
    false
}

/// Quelqu'un a pris le focus -- la barre des taches touchee, une notification.
/// On le reprend, sauf tant que c'est le clavier tactile : le visiteur tape.
fn reprendre_focus(fenetre: tauri::Window) {
    std::thread::sleep(Duration::from_millis(1500));
    // Au plus cinq minutes : un clavier peut rester ouvert le temps d'un
    // formulaire, pas d'une pause dejeuner.
    for _ in 0..600 {
        if fenetre.is_focused().unwrap_or(false) {
            return;
        }
        if clavier_tactile_devant() {
            std::thread::sleep(Duration::from_millis(500));
            continue;
        }
        let _ = fenetre.set_focus();
        return;
    }
}

/// L'exe est en sous-systeme graphique -- pas de console qui clignote au
/// demarrage de la borne --, donc rien de ce qu'il ecrirait sur stderr ne se
/// verrait. Une erreur d'usage se dit dans une boite de message.
#[cfg(windows)]
fn dire(titre: &str, texte: &str) {
    use windows_sys::Win32::UI::WindowsAndMessaging::{MessageBoxW, MB_ICONERROR, MB_OK};
    let en_utf16 = |s: &str| s.encode_utf16().chain(std::iter::once(0)).collect::<Vec<u16>>();
    let (t, x) = (en_utf16(titre), en_utf16(texte));
    unsafe { MessageBoxW(std::ptr::null_mut(), x.as_ptr(), t.as_ptr(), MB_OK | MB_ICONERROR) };
}

#[cfg(not(windows))]
fn dire(titre: &str, texte: &str) {
    eprintln!("{titre} : {texte}");
}

fn main() {
    let options = match lire_options() {
        Ok(o) => o,
        Err(e) => {
            let texte = if e.is_empty() { USAGE.to_string() } else { format!("{e}\n\n{USAGE}") };
            dire("borne", &texte);
            std::process::exit(2);
        }
    };
    let ecran = options.ecran.clone();

    tauri::Builder::default()
        .setup(move |app| {
            let url: tauri::Url = options.url.parse()?;
            let fenetre = WebviewWindowBuilder::new(app, "borne", WebviewUrl::External(url))
                .title(&options.titre)
                .decorations(false)
                .resizable(false)
                .always_on_top(true)
                .initialization_script(GARDE_FOUS)
                .build()?;
            if let Some(m) = choisir_moniteur(app.handle(), &ecran) {
                poser(&fenetre, &m);
            }

            // Windows recompose le bureau quand un capot se ferme ou qu'un
            // cable bouge : le moniteur vise change de place. On regarde
            // toutes les trois secondes et on repose la fenetre si besoin.
            let handle = app.handle().clone();
            std::thread::spawn(move || {
                let mut dernier: Option<(i32, i32, u32, u32)> = None;
                loop {
                    std::thread::sleep(Duration::from_secs(3));
                    let (Some(f), Some(m)) = (handle.get_webview_window("borne"), choisir_moniteur(&handle, &ecran)) else {
                        continue;
                    };
                    let r = rect(&m);
                    if dernier.is_some() && dernier != Some(r) {
                        poser(&f, &m);
                    }
                    dernier = Some(r);
                }
            });
            Ok(())
        })
        .on_window_event(|fenetre, evenement| match evenement {
            // Alt+F4, ou n'importe quelle demande de fermeture : on quitte.
            WindowEvent::CloseRequested { .. } => fenetre.app_handle().exit(0),
            WindowEvent::Focused(false) => {
                let f = fenetre.clone();
                std::thread::spawn(move || reprendre_focus(f));
            }
            _ => {}
        })
        .run(tauri::generate_context!())
        .unwrap_or_else(|e| {
            dire("borne", &format!("lancement impossible : {e}"));
            std::process::exit(1);
        });
}
