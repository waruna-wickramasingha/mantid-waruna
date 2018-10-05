#include "RecoveryThread.h"
#include "ProjectRecovery.h"

bool RecoveryThread::getFailedRun() { return m_failedRunInThread; }

void RecoveryThread::setCheckpoint(Poco::Path checkpoint) {
  m_checkpoint = checkpoint;
}

void RecoveryThread::setProjRecPtr(MantidQt::ProjectRecovery *projectRec) {
  m_projRec = projectRec;
}

void RecoveryThread::run() {
  m_failedRunInThread = !m_projRec->loadRecoveryCheckpoint(m_checkpoint);
}