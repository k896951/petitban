# petitban FreeBSD port

PORTNAME=      petitban
PORTVERSION=   1.3
CATEGORIES=    sysutils
MASTER_SITES=  https://github.com/k896951/petitban/releases/download/v${PORTVERSION}/
DISTFILES=     ${PORTNAME}-${PORTVERSION}.tar.gz
MAINTAINER=    metanole@gmail.com
COMMENT=       A simple IP address ban daemon using ipfw2 for FreeBSD.
LICENSE=       BSD2CLAUSE
USES=          python:run shebangfix
RUN_DEPENDS+=  ${PYTHON_PKGNAMEPREFIX}websockets>=16.0:devel/py-websockets@${PY_FLAVOR}
SHEBANG_REGEX= ^(petitban_daemon\.py|petitban_send\.py)$
SHEBANG_FILES= petitban_daemon.py petitban_send.py
NO_BUILD=      yes
USE_RC_SUBR=   petitban_daemon
SUB_LIST+=     PYTHON_CMD=${PYTHON_CMD}
do-install:
	${INSTALL_SCRIPT} ${WRKSRC}/petitban_daemon.py         ${STAGEDIR}${PREFIX}/bin/petitban_daemon.py
	${INSTALL_SCRIPT} ${WRKSRC}/petitban_send.py           ${STAGEDIR}${PREFIX}/bin/petitban_send.py
	${INSTALL_SCRIPT} ${WRKSRC}/petitban_wrapper.sh.sample ${STAGEDIR}${PREFIX}/bin/petitban_wrapper.sh.sample
	${INSTALL_DATA}   ${WRKSRC}/petitban.conf.sample       ${STAGEDIR}${PREFIX}/etc/petitban.conf.sample

.include <bsd.port.mk>

