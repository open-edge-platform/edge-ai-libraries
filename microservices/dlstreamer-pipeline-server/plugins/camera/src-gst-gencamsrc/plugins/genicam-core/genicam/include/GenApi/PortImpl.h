//-----------------------------------------------------------------------------
//  (c) 2006 by Basler Vision Technologies
//  Section: Vision Components
//  Project: GenApi
//  Author:  Fritz Dierks
//  $Header$
//
//  License: This file is published under the license of the EMVA GenICam  Standard Group.
//  A text file describing the legal terms is included in  your installation as 'GenICam_license.pdf'.
//  If for some reason you are missing  this file please contact the EMVA or visit the website
//  (http://www.genicam.org) for a full copy.
//
//  THIS SOFTWARE IS PROVIDED BY THE EMVA GENICAM STANDARD GROUP "AS IS"
//  AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO,
//  THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR
//  PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE EMVA GENICAM STANDARD  GROUP
//  OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,  SPECIAL,
//  EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT  LIMITED TO,
//  PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,  DATA, OR PROFITS;
//  OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY  THEORY OF LIABILITY,
//  WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT  (INCLUDING NEGLIGENCE OR OTHERWISE)
//  ARISING IN ANY WAY OUT OF THE USE  OF THIS SOFTWARE, EVEN IF ADVISED OF THE
//  POSSIBILITY OF SUCH DAMAGE.
//-----------------------------------------------------------------------------
/*!
\file
\brief    Definition of CPortImpl
\ingroup GenApi_PublicUtilities
*/

#ifndef GENAPI_PORTIMPL_H
#define GENAPI_PORTIMPL_H

#include <Base/GCException.h>
#include <GenApi/GenApiDll.h>
#include <GenApi/Types.h>
#include <GenApi/IPortConstruct.h>
#include <GenApi/IPortRecorder.h>
#include <GenApi/Pointer.h>

#ifdef _MSC_VER
#   pragma warning( push )
#   pragma warning( disable : 4251 )  // enApi::CPortImpl::m_ptrPort' : class 'GenApi::CPointer<T>' needs to have dll-interface
#   pragma warning( disable : 4275 ) // DLL interface (this is a bug)
#   pragma warning( disable : 4068 ) // unknown pragma; refers to BullsEyeCoverage
#endif

namespace GENAPI_NAMESPACE
{
    //*************************************************************
    // CPortImpl class
    //*************************************************************

    /**
    \brief Standard implementation for a port
    //! \ingroup GenApi_PublicUtilities
    */
    class CPortImpl : public IPortConstruct, public IPortReplay
    {
    public:
        //! Constructor
        CPortImpl()
        {
        }

        //! Destructor
        virtual ~CPortImpl()
        {
        }

        /*---------------------------------------------------------------*/
        // IBase ==> You need to override this method
        /*---------------------------------------------------------------*/

        //! Get the access mode of the node
        /*! Driver closed => NI, Driver open => RW, analysing a struct, RO */
        virtual EAccessMode GetAccessMode() const = 0;

        /*---------------------------------------------------------------*/
        // IPort ==> You need to override these methods
        /*---------------------------------------------------------------*/

        //! Reads a chunk of bytes from the port
        virtual void Read(void *pBuffer, int64_t Address, int64_t Length) = 0;

        //! Writes a chunk of bytes to the port
        virtual void Write(const void *pBuffer, int64_t Address, int64_t Length) = 0;

        /*---------------------------------------------------------------*/
        // IPortConstruct implementation (without IPort & IBase)
        /*---------------------------------------------------------------*/

        //! Sets pointer the real port implementation; this function may called only once
        virtual void SetPortImpl(IPort* pPort)
        {
            m_ptrPort = pPort;
            assert(m_ptrPort.IsValid());
        }

        //! Determines if the port adapter must perform an endianess swap
        virtual EYesNo GetSwapEndianess()
        {
            return No;
        }


        //---------------------------------------------------------------
        // IPortReplay implementation
        //---------------------------------------------------------------

        //! sends the commands to the camera.
        /*! the default implementation just walks the list and issues each command
        using the WriteRegister method. Depending on the capabilities of
        the transport layer the implementation can however use a special command
        which sends all register write commands as one package.
        */
        virtual void Replay( IPortWriteList *pPortRecorder, bool Invalidate = true )
        {
            if(pPortRecorder)
                pPortRecorder->Replay(this);

            if(Invalidate)
                InvalidateNode();
        }

        // Invalidate the node
        void InvalidateNode()
        {
            if(m_ptrPort.IsValid())
                m_ptrPort->InvalidateNode();
        }

    private:
        //! Pointer to the node holding a reference to this implementation
        CNodePtr m_ptrPort;

    };
}

#ifdef _MSC_VER
#   pragma warning(pop)
#endif
#endif // ifndef GENAPI_PORTIMPL_H
