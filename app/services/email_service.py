"""
Email service using Brevo (Sendinblue) transactional email API.
API key is read from BREVO_API_KEY environment variable.
"""
import logging
import httpx
from app.core.config import settings

logger = logging.getLogger(__name__)

BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"


async def _send(to_email: str, to_name: str, subject: str, html: str) -> bool:
    if not settings.BREVO_API_KEY:
        logger.warning("BREVO_API_KEY not configured — email not sent to %s", to_email)
        return False

    payload = {
        "sender": {"name": settings.EMAILS_FROM_NAME, "email": settings.EMAILS_FROM_EMAIL},
        "to": [{"email": to_email, "name": to_name}],
        "subject": subject,
        "htmlContent": html,
    }
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "api-key": settings.BREVO_API_KEY,
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(BREVO_API_URL, json=payload, headers=headers)
            if resp.status_code not in (200, 201):
                logger.error("Brevo API error %s: %s", resp.status_code, resp.text)
                return False
            return True
    except Exception as exc:
        logger.error("Email send failed: %s", exc)
        return False


def _base_template(content: str) -> str:
    return f"""
<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>TAXUP</title>
</head>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f1f5f9;padding:32px 0;">
    <tr>
      <td align="center">
        <table width="560" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,.08);">
          <!-- Header -->
          <tr>
            <td style="background:linear-gradient(135deg,#1e3a5f,#1e40af);padding:28px 32px;text-align:center;">
              <h1 style="margin:0;color:#ffffff;font-size:22px;font-weight:800;letter-spacing:2px;">TAXUP</h1>
              <p style="margin:4px 0 0;color:#93c5fd;font-size:12px;">Plateforme Nationale d'Audit Digital Fiscal</p>
            </td>
          </tr>
          <!-- Body -->
          <tr>
            <td style="padding:32px;">
              {content}
            </td>
          </tr>
          <!-- Footer -->
          <tr>
            <td style="background:#f8fafc;border-top:1px solid #e2e8f0;padding:16px 32px;text-align:center;">
              <p style="margin:0;color:#94a3b8;font-size:11px;">
                © {__import__('datetime').date.today().year} TAXUP — Tous droits réservés<br/>
                Cet email a été envoyé automatiquement, merci de ne pas y répondre.
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""


async def send_account_created_email(
    to_email: str,
    full_name: str,
    username: str,
    password: str,
    role: str,
) -> bool:
    """Send welcome email with login credentials when admin creates an account."""
    role_labels = {
        "CITOYEN": "Citoyen",
        "OPERATEUR_MOBILE": "Opérateur Mobile",
        "AUDITEUR_FISCAL": "Auditeur Fiscal",
        "AGENT_DGID": "Agent DGID",
        "ADMIN": "Administrateur",
    }
    role_label = role_labels.get(role, role)

    content = f"""
      <h2 style="margin:0 0 8px;color:#1e3a5f;font-size:20px;">Bienvenue sur TAXUP, {full_name.split()[0]} !</h2>
      <p style="margin:0 0 24px;color:#64748b;font-size:14px;">
        Votre compte a été créé par l'administrateur. Voici vos informations de connexion :
      </p>

      <table width="100%" cellpadding="0" cellspacing="0" style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:8px;margin-bottom:24px;">
        <tr>
          <td style="padding:20px 24px;">
            <table width="100%" cellpadding="0" cellspacing="0">
              <tr>
                <td style="padding:6px 0;">
                  <span style="color:#64748b;font-size:13px;">Nom complet</span><br/>
                  <strong style="color:#1e3a5f;font-size:15px;">{full_name}</strong>
                </td>
              </tr>
              <tr><td style="border-top:1px solid #dbeafe;padding:6px 0 0;"></td></tr>
              <tr>
                <td style="padding:6px 0;">
                  <span style="color:#64748b;font-size:13px;">Identifiant de connexion</span><br/>
                  <strong style="color:#1e3a5f;font-size:15px;">{username}</strong>
                </td>
              </tr>
              <tr><td style="border-top:1px solid #dbeafe;padding:6px 0 0;"></td></tr>
              <tr>
                <td style="padding:6px 0;">
                  <span style="color:#64748b;font-size:13px;">Mot de passe temporaire</span><br/>
                  <strong style="color:#1e40af;font-size:17px;font-family:monospace;letter-spacing:1px;">{password}</strong>
                </td>
              </tr>
              <tr><td style="border-top:1px solid #dbeafe;padding:6px 0 0;"></td></tr>
              <tr>
                <td style="padding:6px 0;">
                  <span style="color:#64748b;font-size:13px;">Rôle assigné</span><br/>
                  <strong style="color:#1e3a5f;font-size:15px;">{role_label}</strong>
                </td>
              </tr>
            </table>
          </td>
        </tr>
      </table>

      <div style="background:#fef3c7;border:1px solid #fcd34d;border-radius:8px;padding:14px 18px;margin-bottom:24px;">
        <p style="margin:0;color:#92400e;font-size:13px;">
          <strong>Important :</strong> Pour des raisons de sécurité, changez votre mot de passe dès votre première connexion.
        </p>
      </div>

      <div style="text-align:center;">
        <a href="https://taxup.gn/login" style="display:inline-block;background:#1e40af;color:#ffffff;text-decoration:none;font-weight:700;font-size:14px;padding:14px 32px;border-radius:8px;">
          Se connecter maintenant
        </a>
      </div>
    """
    return await _send(
        to_email,
        full_name,
        "Vos identifiants de connexion TAXUP",
        _base_template(content),
    )


async def send_welcome_email(
    to_email: str,
    full_name: str,
    username: str,
) -> bool:
    """Send welcome email after self-registration."""
    content = f"""
      <h2 style="margin:0 0 8px;color:#1e3a5f;font-size:20px;">Bienvenue sur TAXUP, {full_name.split()[0]} !</h2>
      <p style="margin:0 0 24px;color:#64748b;font-size:14px;">
        Votre compte a été créé avec succès. Vous pouvez dès maintenant vous connecter à la plateforme.
      </p>

      <table width="100%" cellpadding="0" cellspacing="0" style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:8px;margin-bottom:24px;">
        <tr>
          <td style="padding:20px 24px;">
            <table width="100%" cellpadding="0" cellspacing="0">
              <tr>
                <td style="padding:6px 0;">
                  <span style="color:#64748b;font-size:13px;">Nom complet</span><br/>
                  <strong style="color:#1e3a5f;font-size:15px;">{full_name}</strong>
                </td>
              </tr>
              <tr><td style="border-top:1px solid #dbeafe;padding:6px 0 0;"></td></tr>
              <tr>
                <td style="padding:6px 0;">
                  <span style="color:#64748b;font-size:13px;">Identifiant de connexion</span><br/>
                  <strong style="color:#1e3a5f;font-size:15px;">{username}</strong>
                </td>
              </tr>
            </table>
          </td>
        </tr>
      </table>

      <div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:14px 18px;margin-bottom:24px;">
        <p style="margin:0;color:#166534;font-size:13px;">
          <strong>Conseil :</strong> Pour la sécurité de votre compte, utilisez un mot de passe unique et ne le partagez jamais.
        </p>
      </div>

      <div style="text-align:center;">
        <a href="https://taxup.gn/login" style="display:inline-block;background:#1e40af;color:#ffffff;text-decoration:none;font-weight:700;font-size:14px;padding:14px 32px;border-radius:8px;">
          Accéder à mon compte
        </a>
      </div>
    """
    return await _send(
        to_email,
        full_name,
        "Bienvenue sur TAXUP — Compte créé avec succès",
        _base_template(content),
    )


async def send_account_deactivated_email(to_email: str, full_name: str) -> bool:
    """Send email when an account is deactivated."""
    content = f"""
      <h2 style="margin:0 0 8px;color:#991b1b;font-size:20px;">Compte désactivé</h2>
      <p style="margin:0 0 20px;color:#64748b;font-size:14px;">
        Bonjour <strong>{full_name}</strong>,
      </p>
      <p style="margin:0 0 20px;color:#64748b;font-size:14px;">
        Votre compte TAXUP a été <strong style="color:#dc2626;">désactivé</strong> par un administrateur.
        Vous ne pouvez plus accéder à la plateforme jusqu'à réactivation.
      </p>
      <div style="background:#fef2f2;border:1px solid #fecaca;border-radius:8px;padding:14px 18px;margin-bottom:24px;">
        <p style="margin:0;color:#991b1b;font-size:13px;">
          Si vous pensez qu'il s'agit d'une erreur, contactez votre administrateur TAXUP.
        </p>
      </div>
    """
    return await _send(
        to_email,
        full_name,
        "Votre compte TAXUP a été désactivé",
        _base_template(content),
    )


async def send_account_activated_email(to_email: str, full_name: str) -> bool:
    """Send email when an account is reactivated."""
    content = f"""
      <h2 style="margin:0 0 8px;color:#065f46;font-size:20px;">Compte réactivé</h2>
      <p style="margin:0 0 20px;color:#64748b;font-size:14px;">
        Bonjour <strong>{full_name}</strong>,
      </p>
      <p style="margin:0 0 20px;color:#64748b;font-size:14px;">
        Votre compte TAXUP a été <strong style="color:#059669;">réactivé</strong> par un administrateur.
        Vous pouvez de nouveau accéder à la plateforme.
      </p>
      <div style="text-align:center;margin-top:8px;">
        <a href="https://taxup.gn/login" style="display:inline-block;background:#1e40af;color:#ffffff;text-decoration:none;font-weight:700;font-size:14px;padding:14px 32px;border-radius:8px;">
          Se connecter
        </a>
      </div>
    """
    return await _send(
        to_email,
        full_name,
        "Votre compte TAXUP a été réactivé",
        _base_template(content),
    )
