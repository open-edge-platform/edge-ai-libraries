/****************************************************************************
 (c) 2014 by Teledyne DALSA
 Section: Digital Imaging
 Project: GCBase
 Author:  Eric Bourbonnais


 License: This file is published under the license of the EMVA GenICam  Standard Group.
 A text file describing the legal terms is included in  your installation as 'GenICam_license.pdf'.
 If for some reason you are missing  this file please contact the EMVA or visit the website
 (http://www.genicam.org) for a full copy.

 THIS SOFTWARE IS PROVIDED BY THE EMVA GENICAM STANDARD GROUP "AS IS"
 AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO,
 THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR
 PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE EMVA GENICAM STANDARD  GROUP
 OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,  SPECIAL,
 EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT  LIMITED TO,
 PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,  DATA, OR PROFITS;
 OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY  THEORY OF LIABILITY,
 WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT  (INCLUDING NEGLIGENCE OR OTHERWISE)
 ARISING IN ANY WAY OUT OF THE USE  OF THIS SOFTWARE, EVEN IF ADVISED OF THE
 POSSIBILITY OF SUCH DAMAGE.

****************************************************************************/

#ifndef GCBASE_GCARRAY_H
#define GCBASE_GCARRAY_H

#include <Base/GCTypes.h>
namespace GENICAM_NAMESPACE
{
    template< class T>
    class  gcarray
    {
    public:
        gcarray( size_t size) : m_p( NULL)
        {
            if(size)
                m_p = new T[size];
        };
        ~gcarray( ){ if(m_p) delete [] m_p;};
        T* get() const {return m_p;} ;
        T* operator *() {return m_p;} ;
        T operator[](size_t idx) {return m_p[idx];} ;
    private:
       T* m_p;
    };

}

#endif // GCBASE_GCARRAY_H
