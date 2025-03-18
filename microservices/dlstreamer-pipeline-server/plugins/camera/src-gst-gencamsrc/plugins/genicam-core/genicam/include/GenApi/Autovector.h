//-----------------------------------------------------------------------------
//  (c) 2012 by Teledyne DALSA
//  Section: Digital Imaging
//  Project: GenAPI
//  Author:  Eric Bourbonnais
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
//
/*!
\file
\brief   This file contains the public definition of the autovector classes.
\ingroup GenApi_PublicInterface
*/

//////////////////////////////////////////////////////////////////////////////

#ifndef GENAPI_AUTOVECTOR_H
#define GENAPI_AUTOVECTOR_H

#include <vector>
#include <Base/GCTypes.h>
#include <GenApi/GenApiDll.h>

#if defined (_WIN32)
    typedef long ATOMIC_VARIABLE;
#elif (defined(__GNUC__) && (defined (__linux__)) || defined (__APPLE__)) || defined(VXWORKS)
    typedef uint32_t ATOMIC_VARIABLE;
#else
#   error Unsupported platform
#endif

namespace GENAPI_NAMESPACE
{
    /**
    \brief Vector of integers with reference counting
    \ingroup GenApi_PublicInterface
    */
    class GENAPI_DECL int64_autovector_t
    {
    public:
        explicit  int64_autovector_t();
                  int64_autovector_t( const int64_autovector_t& obj );
        explicit  int64_autovector_t( size_t n );
        virtual  ~int64_autovector_t( void );

        int64_autovector_t& operator=( const int64_autovector_t& obj );

        int64_t&       operator[]( size_t uiIndex );
        const int64_t& operator[]( size_t uiIndex ) const;
        size_t         size( void ) const;
    protected:
        std::vector<int64_t>* _pv;
        ATOMIC_VARIABLE* _pCount;
    };
    
    /**
    \brief Vector of doubles with reference counting
    \ingroup GenApi_PublicInterface
    */
    class GENAPI_DECL double_autovector_t
    {
    public:
        explicit  double_autovector_t();
                  double_autovector_t( const double_autovector_t& obj );
        explicit  double_autovector_t( size_t n );
        virtual  ~double_autovector_t( void );

        double_autovector_t& operator=( const double_autovector_t& obj );

        double&       operator[]( size_t uiIndex );
        const double& operator[]( size_t uiIndex ) const;
        size_t        size( void )const;
    protected:
        std::vector<double>* _pv;
        ATOMIC_VARIABLE* _pCount;
    };
}

#endif // GENAPI_AUTOVECTOR_H
