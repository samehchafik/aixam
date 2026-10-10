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
    let url = url_acceptee(&url.ok_or("l'url de la page a ouvrir manque")?)?;
    Ok(Options { url, ecran, titre })
}

/// Seules http et https : un file:// ou une faute de frappe ouvrirait une
/// fenetre vide en plein ecran, que rien ne fermerait sinon Alt+F4.
fn url_acceptee(url: &str) -> Result<String, String> {
    if url.starts_with("http://") || url.starts_with("https://") {
        Ok(url.to_string())
    } else {
        Err(format!("url invalide, il faut http:// ou https:// : {url}"))
    }
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

/// Le point (x, y) tombe-t-il dans ce rectangle d'ecran ? Sorti de `contient`
/// pour etre eprouvable sans moniteur : un Monitor ne se fabrique pas a la
/// main, et c'est cette arithmetique-la qui decide ou une fenetre atterrit.
fn dans_rect(px: i32, py: i32, largeur: u32, hauteur: u32, x: i32, y: i32) -> bool {
    x >= px && y >= py && x < px + largeur as i32 && y < py + hauteur as i32
}

fn contient(m: &Monitor, x: i32, y: i32) -> bool {
    let (p, s) = (m.position(), m.size());
    dans_rect(p.x, p.y, s.width, s.height, x, y)
}

/// Le moniteur demande, ou le plus proche de ce qui a ete demande : un numero
/// trop grand prend le dernier, une position qui n'est plus au coin d'un ecran
/// prend celui qui la contient, et sinon l'ecran principal -- mais jamais rien.
fn choisir_moniteur(app: &tauri::AppHandle, ecran: &Ecran) -> Option<Monitor> {
    let tous = app.available_monitors().ok()?;
    let principal = || app.primary_monitor().ok().flatten().or_else(|| tous.first().cloned());
    match ecran {
        Ecran::Principal => principal(),
        // Pas de repli sur le dernier moniteur : « --ecran 3840 » est une
        // position tronquee, pas un numero, et prendre le dernier ecran
        // aurait pose les deux fenetres au meme endroit sans un mot.
        Ecran::Numero(n) => tous.get(*n).cloned(),
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
///
/// Et ce qu'elle ne doit pas VOIR : Tauri pose `__TAURI_INTERNALS__` dans
/// toute vue qu'il cree. Une page qui le trouve se croit dans l'application
/// empaquetee et cherche ses reglages par les API Tauri -- la borne le
/// faisait, et s'ouvrait sur « Erreur de demarrage ». borne.exe est un
/// navigateur, rien de plus : la page doit se comporter comme dans Chrome.
/// Retirer ces objets ferme du meme coup tout acces a l'IPC depuis une page
/// distante.
const GARDE_FOUS: &str = r#"
for (const nom of ['__TAURI_INTERNALS__', '__TAURI__', '__TAURI_EVENT_PLUGIN_INTERNALS__', '__TAURI_PATTERN__']) {
  try { delete window[nom]; } catch (e) {}
}
document.addEventListener('contextmenu', e => e.preventDefault(), true);
document.addEventListener('gesturestart', e => e.preventDefault(), true);
"#;

/// L'agent utilisateur de borne.exe : celui d'Edge -- le moteur est le meme,
/// WebView2 --, suivi de `SAMS-Borne/<version>`. C'est ce qui distingue, cote
/// serveur, la borne d'un navigateur qui ouvrirait la meme page (voir
/// app/services/client.py). Une marque, pas une securite : un navigateur peut
/// l'imiter. La version de Chrome n'est qu'indicative, rien ne s'en sert.
fn agent_utilisateur() -> String {
    format!(
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) \
         Chrome/141.0.0.0 Safari/537.36 Edg/141.0.0.0 SAMS-Borne/{}",
        env!("CARGO_PKG_VERSION")
    )
}

/// Le clavier tactile de Windows est-il a l'ecran ?
///
/// IFrameworkInputPane est l'API prevue pour cela : elle rend le rectangle du
/// clavier, vide quand il est range -- pour TabTip (Windows 10) comme pour
/// TextInputHost (Windows 11). Regarder qui a le premier plan ne suffisait
/// pas : le clavier ne prend pas le focus (il active l'Explorateur), si bien
/// que la borne le croyait absent, reprenait la main et passait devant lui.
/// A defaut de l'API, on se rabat sur la fenetre de TabTip et sur le premier
/// plan.
#[cfg(windows)]
mod clavier {
    use std::ffi::c_void;
    use windows_sys::core::{GUID, HRESULT};
    use windows_sys::Win32::Foundation::RECT;
    use windows_sys::Win32::System::Com::{
        CoCreateInstance, CoInitializeEx, CLSCTX_INPROC_SERVER, CLSCTX_LOCAL_SERVER, COINIT_APARTMENTTHREADED,
    };
    use windows_sys::Win32::UI::WindowsAndMessaging::{
        FindWindowW, GetClassNameW, GetForegroundWindow, GetWindowTextW, IsWindowVisible,
    };

    const CLSID_FRAMEWORK_INPUT_PANE: GUID = GUID::from_u128(0xD5120AA3_46BA_44C5_822D_CA8092C1FC72);
    const IID_IFRAMEWORK_INPUT_PANE: GUID = GUID::from_u128(0x5752238B_24F0_495A_82F1_2FD593056796);

    /// La table de IFrameworkInputPane : IUnknown, puis Advise,
    /// AdviseWithHWND, Unadvise et Location -- seule cette derniere sert.
    #[repr(C)]
    struct Table {
        _iunknown: [usize; 3],
        _advise: [usize; 3],
        location: unsafe extern "system" fn(*mut c_void, *mut RECT) -> HRESULT,
    }

    /// Le volet du clavier, cree une fois par fil (COM y est initialise).
    pub struct Volet(*mut c_void);

    impl Volet {
        pub fn ouvrir() -> Option<Volet> {
            unsafe {
                CoInitializeEx(std::ptr::null(), COINIT_APARTMENTTHREADED as u32);
                let mut ptr: *mut c_void = std::ptr::null_mut();
                let hr = CoCreateInstance(
                    &CLSID_FRAMEWORK_INPUT_PANE,
                    std::ptr::null_mut(),
                    CLSCTX_INPROC_SERVER | CLSCTX_LOCAL_SERVER,
                    &IID_IFRAMEWORK_INPUT_PANE,
                    &mut ptr,
                );
                (hr >= 0 && !ptr.is_null()).then_some(Volet(ptr))
            }
        }

        /// Some(vrai) si le clavier occupe un rectangle, None si l'API echoue.
        fn rectangle(&self) -> Option<bool> {
            unsafe {
                let table = *(self.0 as *const *const Table);
                let mut r = RECT { left: 0, top: 0, right: 0, bottom: 0 };
                if ((*table).location)(self.0, &mut r) < 0 {
                    return None;
                }
                Some(r.right > r.left && r.bottom > r.top)
            }
        }
    }

    fn texte(f: unsafe extern "system" fn(*mut c_void, *mut u16, i32) -> i32, h: *mut c_void) -> String {
        let mut tampon = [0u16; 128];
        let n = unsafe { f(h, tampon.as_mut_ptr(), tampon.len() as i32) };
        String::from_utf16_lossy(&tampon[..n.max(0) as usize])
    }

    pub fn visible(volet: Option<&Volet>) -> bool {
        if let Some(oui) = volet.and_then(Volet::rectangle) {
            return oui;
        }
        unsafe {
            let classe: Vec<u16> = "IPTip_Main_Window\0".encode_utf16().collect();
            let tabtip = FindWindowW(classe.as_ptr(), std::ptr::null());
            if !tabtip.is_null() && IsWindowVisible(tabtip) != 0 {
                return true;
            }
            let h = GetForegroundWindow();
            if h.is_null() {
                return false;
            }
            match texte(GetClassNameW, h).as_str() {
                "IPTip_Main_Window" => true,
                "Windows.UI.Core.CoreWindow" => {
                    let titre = texte(GetWindowTextW, h).to_lowercase();
                    titre.contains("text input") || titre.contains("clavier") || titre.contains("entrée")
                }
                _ => false,
            }
        }
    }
}

#[cfg(not(windows))]
mod clavier {
    pub struct Volet;
    impl Volet {
        pub fn ouvrir() -> Option<Volet> {
            None
        }
    }
    pub fn visible(_: Option<&Volet>) -> bool {
        false
    }
}

/// Le clavier tactile est-il ouvert ? Pour le fil qui reprend le focus.
fn clavier_tactile_ouvert() -> bool {
    clavier::visible(clavier::Volet::ouvrir().as_ref())
}

/// Quelqu'un a pris le focus -- la barre des taches touchee, une notification.
/// On le reprend, sauf tant que le clavier tactile de Windows est ouvert.
///
/// La borne a desormais son propre clavier, dans la page, et ses champs
/// n'appellent plus celui de Windows. Un fil qui retirait le premier plan a la
/// fenetre tant que ce dernier etait ouvert, et lui rendait le focus a sa
/// fermeture, a ete retire : ses allers-retours du focus faisaient clignoter
/// le clavier de la page.
fn reprendre_focus(fenetre: tauri::Window) {
    std::thread::sleep(Duration::from_millis(1500));
    if fenetre.is_focused().unwrap_or(false) || clavier_tactile_ouvert() {
        return;
    }
    let _ = fenetre.set_focus();
}

/// Le journal de borne.exe : `.run/borne.log` du projet (deux dossiers au-dessus
/// de bin/win/), a defaut le dossier temporaire. Une ligne par evenement, avec
/// l'heure UTC, le pid et le titre : les deux fenetres y ecrivent ensemble, et
/// c'est ce qui dit laquelle s'arrete, et pourquoi.
static TITRE: std::sync::OnceLock<String> = std::sync::OnceLock::new();

fn journal() -> std::path::PathBuf {
    let run = std::env::current_exe()
        .ok()
        .and_then(|e| e.parent()?.parent()?.parent().map(|r| r.join(".run")))
        .filter(|d| d.is_dir());
    run.unwrap_or_else(std::env::temp_dir).join("borne.log")
}

fn noter(message: &str) {
    use std::io::Write;
    let s = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0);
    let ligne = format!(
        "{:02}:{:02}:{:02} UTC  pid {}  {}  {}\n",
        (s / 3600) % 24,
        (s / 60) % 60,
        s % 60,
        std::process::id(),
        TITRE.get().map(String::as_str).unwrap_or("?"),
        message
    );
    if let Ok(mut f) = std::fs::OpenOptions::new().create(true).append(true).open(journal()) {
        let _ = f.write_all(ligne.as_bytes());
    }
}

/// L'exe est en sous-systeme graphique -- pas de console qui clignote au
/// demarrage de la borne --, donc rien de ce qu'il ecrirait sur stderr ne se
/// verrait. Une erreur d'usage se dit dans une boite de message.
#[cfg(windows)]
fn dire(titre: &str, texte: &str) {
    use windows_sys::Win32::UI::WindowsAndMessaging::{MessageBoxW, MB_ICONERROR, MB_OK};
    let (t, x) = (titre.to_string(), texte.to_string());
    let fil = std::thread::spawn(move || {
        let en_utf16 = |s: &str| s.encode_utf16().chain(std::iter::once(0)).collect::<Vec<u16>>();
        let (t, x) = (en_utf16(&t), en_utf16(&x));
        unsafe { MessageBoxW(std::ptr::null_mut(), x.as_ptr(), t.as_ptr(), MB_OK | MB_ICONERROR) };
    });
    // La boite est montree sur un fil, et l'on n'attend pas indefiniment
    // qu'on y clique. Lancee par le lanceur au demarrage de la borne,
    // personne n'est la pour le faire : le processus restait vivant sur sa
    // boite, et le lanceur -- qui verifie que les processus survivent -- le
    // comptait comme une fenetre ouverte. Il annoncait « 2 fenetres
    // ouvertes » alors que les deux avaient echoue.
    let debut = std::time::Instant::now();
    while !fil.is_finished() && debut.elapsed() < Duration::from_secs(20) {
        std::thread::sleep(Duration::from_millis(100));
    }
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
    let _ = TITRE.set(options.titre.clone());
    noter(&format!("demarrage : {} --ecran {:?} (borne.exe {})", options.url, ecran, env!("CARGO_PKG_VERSION")));
    std::panic::set_hook(Box::new(|info| noter(&format!("PANIQUE : {info}"))));

    tauri::Builder::default()
        .setup(move |app| {
            let url: tauri::Url = options.url.parse()?;
            let fenetre = WebviewWindowBuilder::new(app, "borne", WebviewUrl::External(url))
                .title(&options.titre)
                .decorations(false)
                .resizable(false)
                .always_on_top(true)
                .user_agent(&agent_utilisateur())
                .initialization_script(GARDE_FOUS)
                .build()?;
            let vus: Vec<String> = app
                .available_monitors()
                .unwrap_or_default()
                .iter()
                .map(|m| {
                    let (x, y, l, h) = rect(m);
                    format!("{l}x{h} en {x},{y}")
                })
                .collect();
            noter(&format!("ecrans vus : {}", vus.join(" ; ")));
            match choisir_moniteur(app.handle(), &ecran) {
                Some(m) => {
                    let (x, y, l, h) = rect(&m);
                    noter(&format!("ecran choisi : {l}x{h} en {x},{y}"));
                    poser(&fenetre, &m)
                }
                None => {
                    noter("ecran demande introuvable : sortie (code 2)");
                    let n = app.available_monitors().map(|m| m.len()).unwrap_or(0);
                    dire("borne", &format!(
                        "ecran demande introuvable ({ecran:?}) : cette machine en compte {n}.\n\n                         Un numero designe un moniteur (0, 1, ...) ; pour une position, il faut\n                         les deux valeurs, par exemple --ecran 3840,0."));
                    std::process::exit(2);
                }
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
                        noter(&format!("ecran deplace : {}x{} en {},{} -- fenetre reposee", r.2, r.3, r.0, r.1));
                        poser(&f, &m);
                    }
                    dernier = Some(r);
                }
            });
            Ok(())
        })
        .on_window_event(|fenetre, evenement| match evenement {
            // Alt+F4, ou n'importe quelle demande de fermeture : on quitte.
            WindowEvent::CloseRequested { .. } => {
                noter("fermeture demandee (Alt+F4 ou Windows) : sortie");
                fenetre.app_handle().exit(0)
            }
            WindowEvent::Destroyed => noter("fenetre detruite"),
            WindowEvent::Focused(false) => {
                let f = fenetre.clone();
                std::thread::spawn(move || reprendre_focus(f));
            }
            _ => {}
        })
        .build(tauri::generate_context!())
        .unwrap_or_else(|e| {
            noter(&format!("lancement impossible : {e}"));
            dire("borne", &format!("lancement impossible : {e}"));
            std::process::exit(1);
        })
        .run(|_, evenement| match evenement {
            tauri::RunEvent::ExitRequested { code, .. } => noter(&format!("sortie demandee (code {code:?})")),
            tauri::RunEvent::Exit => noter("fin du programme"),
            _ => {}
        });
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn ecran_par_defaut_et_formes_acceptees() {
        assert!(matches!(analyser_ecran("principal"), Ok(Ecran::Principal)));
        assert!(matches!(analyser_ecran("PRINCIPAL"), Ok(Ecran::Principal)));
        assert!(matches!(analyser_ecran("0"), Ok(Ecran::Numero(0))));
        assert!(matches!(analyser_ecran("2"), Ok(Ecran::Numero(2))));
        // La forme que le lanceur engendre passe : c'est celle qui survit a un
        // moniteur renumerote.
        assert!(matches!(analyser_ecran("3840,0"), Ok(Ecran::Position(3840, 0))));
        assert!(matches!(analyser_ecran(" 3840 , 2160 "), Ok(Ecran::Position(3840, 2160))));
        // Un ecran a gauche du principal a une abscisse negative.
        assert!(matches!(analyser_ecran("-1920,0"), Ok(Ecran::Position(-1920, 0))));
        // « 3840 » seul est un NUMERO, pas une position : c'est bien lu ainsi,
        // et c'est pourquoi un numero hors de portee doit se dire plutot que
        // de retomber sur le dernier ecran -- une position tronquee aurait
        // sinon pose les deux fenetres au meme endroit, en silence.
        assert!(matches!(analyser_ecran("3840"), Ok(Ecran::Numero(3840))));
    }

    #[test]
    fn une_valeur_illisible_est_refusee_pas_ignoree() {
        // Retomber en silence sur l'ecran principal poserait les deux fenetres
        // l'une sur l'autre, sans que rien ne le dise.
        for v in ["", "gauche", "3840,", ",0", "3840,0,0", "a,b"] {
            assert!(analyser_ecran(v).is_err(), "{v:?} aurait du etre refuse");
        }
    }

    #[test]
    fn le_point_tombe_dans_le_bon_ecran() {
        // Deux moniteurs cote a cote : 3200x2000 a l'origine, 1920x1080 a sa
        // droite. C'est la disposition de la borne, capot ouvert.
        assert!(dans_rect(0, 0, 3200, 2000, 0, 0));
        assert!(dans_rect(0, 0, 3200, 2000, 3199, 1999));
        // Le bord droit appartient au voisin, pas a lui : sans le `<` strict,
        // une fenetre posee en 3200,0 aurait pu revenir sur le premier ecran.
        assert!(!dans_rect(0, 0, 3200, 2000, 3200, 0));
        assert!(dans_rect(3200, 0, 1920, 1080, 3200, 0));
        assert!(!dans_rect(3200, 0, 1920, 1080, 5120, 0));
    }

    #[test]
    fn l_agent_utilisateur_porte_la_marque_de_la_borne() {
        // Le serveur cherche cette marque (app/services/client.py).
        let ua = agent_utilisateur();
        assert!(ua.ends_with(&format!(" SAMS-Borne/{}", env!("CARGO_PKG_VERSION"))), "{ua}");
        assert!(ua.starts_with("Mozilla/5.0 (Windows NT 10.0"), "{ua}");
        assert!(!ua.contains("  "), "{ua}");
    }

    #[test]
    fn l_url_doit_etre_http() {
        // Un chemin de fichier ou une faute de frappe ouvrirait une fenetre
        // vide en plein ecran, sans rien pour la fermer sinon Alt+F4.
        for v in ["localhost:8080", "file:///C:/x.html", "/kiosk/", "javascript:1"] {
            assert!(url_acceptee(v).is_err(), "{v:?} aurait du etre refuse");
        }
        assert!(url_acceptee("http://localhost:8080/kiosk/").is_ok());
        assert!(url_acceptee("https://aixam.ifrit.fr/#/display").is_ok());
    }
}
