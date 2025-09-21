# -*- coding: utf-8 -*-
import os
from typing import Dict, List, Tuple

from PySide6.QtCore import QObject, QThread, Signal

from qgitc.applicationbase import ApplicationBase
from qgitc.cancelevent import CancelEvent
from qgitc.common import fullRepoDir, logger
from qgitc.gitutils import Git
from qgitc.submoduleexecutor import SubmoduleExecutor


class BranchCompareFetcher(QObject):
    """Fetches branch comparison data across repositories"""

    branchesAvailable = Signal(list)  # List[str] - available branches
    filesAvailable = Signal(list)     # List[Tuple[str, str, str]] - (file, repoDir, status)
    diffAvailable = Signal(list, list)  # lineItems, fileItems
    fetchFinished = Signal()
    errorOccurred = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        
        self._executor = SubmoduleExecutor(self)
        self._executor.finished.connect(self._onExecutorFinished)
        
        self._currentOperation = None
        self._diffLines = []

    def fetchBranches(self):
        """Fetch available branches from main repository"""
        if not Git.REPO_DIR:
            self.branchesAvailable.emit([])
            return
        
        self._currentOperation = "branches"
        
        # Use main repo to get branches
        submodules = {".": None}
        self._executor.submit(submodules, self._doFetchBranches)

    def fetchComparison(self, baseBranch: str, compareBranch: str, submodules: List[str]):
        """Fetch file comparison between branches"""
        self._currentOperation = "comparison"
        self._baseBranch = baseBranch
        self._compareBranch = compareBranch
        
        # Prepare submodules dict
        submoduleData = {}
        for submodule in submodules:
            submoduleData[submodule] = (baseBranch, compareBranch)
        
        self._executor.submit(submoduleData, self._doFetchComparison)

    def fetchFileDiff(self, baseBranch: str, compareBranch: str, filePath: str, repoDir: str):
        """Fetch diff for specific file"""
        self._currentOperation = "diff"
        self._diffLines = []
        
        # Single submodule operation
        submodules = {repoDir: (baseBranch, compareBranch, filePath)}
        self._executor.submit(submodules, self._doFetchFileDiff)

    def cancel(self):
        """Cancel current operation"""
        if self._executor:
            self._executor.cancel()

    def _doFetchBranches(self, submodule: str, userData, cancelEvent: CancelEvent):
        """Fetch branches from repository"""
        try:
            repoDir = fullRepoDir(submodule)
            
            # Get all branches (local and remote)
            out, error = Git.run(["branch", "-a"], repoDir=repoDir)
            if error:
                logger.warning(f"Failed to get branches: {error}")
                ApplicationBase.instance().postEvent(self.parent(), 
                    BranchInfoEvent([]))
                return
            
            branches = []
            for line in out.strip().split('\n'):
                line = line.strip()
                if not line:
                    continue
                
                # Remove current branch marker
                if line.startswith('* '):
                    line = line[2:]
                
                # Skip HEAD pointer
                if 'HEAD ->' in line:
                    continue
                
                # Handle remote branches
                if line.startswith('remotes/'):
                    # Extract branch name from remotes/origin/branch-name
                    parts = line.split('/')
                    if len(parts) >= 3:
                        branch_name = '/'.join(parts[2:])
                        if branch_name not in branches:
                            branches.append(branch_name)
                else:
                    # Local branch
                    if line not in branches:
                        branches.append(line)
            
            # Sort branches
            branches.sort()
            
            # Import here to avoid circular imports
            from qgitc.branchcomparewindow import BranchInfoEvent
            ApplicationBase.instance().postEvent(self.parent(), 
                BranchInfoEvent(branches))
                
        except Exception as e:
            logger.error(f"Error fetching branches: {str(e)}")
            # Import here to avoid circular imports
            from qgitc.branchcomparewindow import BranchInfoEvent
            ApplicationBase.instance().postEvent(self.parent(), 
                BranchInfoEvent([]))

    def _doFetchComparison(self, submodule: str, userData: Tuple[str, str], cancelEvent: CancelEvent):
        """Fetch comparison between branches for a submodule"""
        if cancelEvent.isSet():
            return
            
        baseBranch, compareBranch = userData
        
        try:
            repoDir = fullRepoDir(submodule)
            
            # Use git diff to get changed files between branches
            args = ["diff", "--name-status", f"{baseBranch}..{compareBranch}"]
            out, error = Git.run(args, repoDir=repoDir)
            
            if cancelEvent.isSet():
                return
                
            if error:
                logger.warning(f"Failed to get diff for {submodule}: {error}")
                return
            
            files = []
            for line in out.strip().split('\n'):
                if not line.strip():
                    continue
                
                parts = line.split('\t')
                if len(parts) >= 2:
                    status = parts[0]
                    filePath = parts[1]
                    
                    # Handle renamed files (R100 file1 -> file2)
                    if status.startswith('R') and len(parts) >= 3:
                        filePath = parts[2]  # Use new file name
                    
                    files.append((filePath, submodule, status))
            
            if files:
                # Import here to avoid circular imports
                from qgitc.branchcomparewindow import FileListReadyEvent
                ApplicationBase.instance().postEvent(self.parent(), 
                    FileListReadyEvent(files))
                    
        except Exception as e:
            logger.error(f"Error fetching comparison for {submodule}: {str(e)}")

    def _doFetchFileDiff(self, submodule: str, userData: Tuple[str, str, str], cancelEvent: CancelEvent):
        """Fetch diff content for specific file"""
        if cancelEvent.isSet():
            return
            
        baseBranch, compareBranch, filePath = userData
        
        try:
            repoDir = fullRepoDir(submodule)
            
            # Get diff content
            args = ["diff", f"{baseBranch}..{compareBranch}", "--", filePath]
            out, error = Git.run(args, repoDir=repoDir)
            
            if cancelEvent.isSet():
                return
                
            if error:
                logger.warning(f"Failed to get file diff: {error}")
                return
            
            # Parse diff output into line items (similar to DiffFetcher)
            self._parseDiffOutput(out)
            
        except Exception as e:
            logger.error(f"Error fetching file diff: {str(e)}")

    def _parseDiffOutput(self, diffOutput: str):
        """Parse git diff output into line items"""
        from qgitc.diffview import DiffTextLine, InfoTextLine
        
        lineItems = []
        lines = diffOutput.split('\n')
        
        for line in lines:
            if line.startswith('diff --git'):
                # File header
                lineItems.append(InfoTextLine(line, None))
            elif line.startswith('index '):
                # Index line
                lineItems.append(InfoTextLine(line, None))
            elif line.startswith('--- ') or line.startswith('+++ '):
                # File markers
                lineItems.append(InfoTextLine(line, None))
            elif line.startswith('@@'):
                # Hunk header
                lineItems.append(InfoTextLine(line, None))
            elif line.startswith('+'):
                # Addition
                lineItems.append(DiffTextLine(line, '+'))
            elif line.startswith('-'):
                # Deletion  
                lineItems.append(DiffTextLine(line, '-'))
            else:
                # Context line
                lineItems.append(DiffTextLine(line, ' '))
        
        # Emit the diff content
        self.diffAvailable.emit(lineItems, [])

    def _onExecutorFinished(self):
        """Handle executor completion"""
        self.fetchFinished.emit()
