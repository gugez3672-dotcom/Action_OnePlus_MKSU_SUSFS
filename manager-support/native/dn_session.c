#define _GNU_SOURCE
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/inotify.h>
#include <sys/ioctl.h>
#include <sys/prctl.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/un.h>
#include <sys/wait.h>
#include <termios.h>
#include <unistd.h>

/* One supervisor per live session/task. No global daemon, mount or cgroup edits.
 * Subreaper adoption keeps double-fork/setsid descendants attributable after the
 * original script exits. Every signal verifies PID starttime; no name matching. */
typedef struct { pid_t pid, parent; unsigned long long start; char state; } Proc;
static volatile sig_atomic_t stopping;
static const char *control_dir;
static uid_t app_uid;
static int same_process(Proc p);
static volatile sig_atomic_t resized=1;
#define HISTORY_SIZE (64*1024)
#define FRAME_SIZE 4096
static unsigned char history[HISTORY_SIZE], pending[HISTORY_SIZE];
static size_t history_size, pending_size, pending_pos;
static unsigned char input_bytes[FRAME_SIZE];
static size_t input_size, input_pos;
static void resize_signal(int sig){(void)sig;resized=1;}
static int socket_address(struct sockaddr_un *address){
    memset(address,0,sizeof *address);address->sun_family=AF_UNIX;
    int n=snprintf(address->sun_path,sizeof address->sun_path,"%s/stream",control_dir);
    return n>0&&(size_t)n<sizeof address->sun_path;
}
static int view_detached(void){char path[4096],value[16]={0};
    snprintf(path,sizeof path,"%s/view",control_dir);int fd=open(path,O_RDONLY|O_NOFOLLOW|O_CLOEXEC);
    if(fd<0)return 0;ssize_t n=read(fd,value,sizeof value-1);close(fd);
    return n>=6&&!memcmp(value,"DETACH",6);
}
static int write_all(int fd,const void *bytes,size_t size){
    const unsigned char *p=bytes;while(size){ssize_t n=write(fd,p,size);
        if(n<0&&errno==EINTR)continue;if(n<=0)return 0;p+=n;size-=(size_t)n;}return 1;
}
static void remember_output(const unsigned char *bytes,size_t size){
    if(size>=HISTORY_SIZE){bytes+=size-HISTORY_SIZE;size=HISTORY_SIZE;history_size=0;}
    if(history_size+size>HISTORY_SIZE){size_t remove=history_size+size-HISTORY_SIZE;
        memmove(history,history+remove,history_size-remove);history_size-=remove;}
    memcpy(history+history_size,bytes,size);history_size+=size;
}
static int flush_output(int client){
    if(pending_pos==pending_size){pending_pos=pending_size=0;return 1;}
    unsigned char frame[FRAME_SIZE+1];frame[0]='D';size_t n=pending_size-pending_pos;
    if(n>FRAME_SIZE)n=FRAME_SIZE;memcpy(frame+1,pending+pending_pos,n);
    ssize_t sent=send(client,frame,n+1,MSG_DONTWAIT|MSG_NOSIGNAL);
    if(sent<0&&(errno==EAGAIN||errno==EWOULDBLOCK))return 1;
    if(sent!=(ssize_t)n+1)return 0;pending_pos+=n;
    if(pending_pos==pending_size)pending_pos=pending_size=0;return 1;
}
static int listen_output(void){
    struct sockaddr_un address;if(!socket_address(&address))return -1;
    int fd=socket(AF_UNIX,SOCK_SEQPACKET|SOCK_CLOEXEC|SOCK_NONBLOCK,0);if(fd<0)return -1;
    unlink(address.sun_path);
    if(bind(fd,(struct sockaddr*)&address,sizeof address)||chmod(address.sun_path,0600)||
       chown(address.sun_path,app_uid,(gid_t)app_uid)||listen(fd,1)){close(fd);unlink(address.sun_path);return -1;}
    return fd;
}
static int attach_output(Proc owner){
    struct sockaddr_un address;if(!socket_address(&address))return 64;
    int connection=socket(AF_UNIX,SOCK_SEQPACKET|SOCK_CLOEXEC,0);if(connection<0)return 71;
    if(connect(connection,(struct sockaddr*)&address,sizeof address)){close(connection);return 69;}
    struct termios original;int has_tty=tcgetattr(0,&original)==0;
    if(has_tty){struct termios raw=original;cfmakeraw(&raw);tcsetattr(0,TCSANOW,&raw);}
    signal(SIGWINCH,resize_signal);signal(SIGPIPE,SIG_IGN);
    unsigned char frame[FRAME_SIZE+1];int result=0;
    while(!view_detached()&&same_process(owner)){
        if(resized){resized=0;struct winsize size={.ws_row=24,.ws_col=80};ioctl(0,TIOCGWINSZ,&size);
            frame[0]='R';memcpy(frame+1,&size,sizeof size);
            if(send(connection,frame,1+sizeof size,MSG_NOSIGNAL)<0)break;}
        struct pollfd p[2]={{.fd=connection,.events=POLLIN},{.fd=0,.events=POLLIN}};
        int polled=poll(p,2,200);if(polled<0&&errno==EINTR)continue;if(polled<0)break;
        if(p[0].revents&POLLIN){ssize_t n=recv(connection,frame,sizeof frame,0);if(n<=0)break;
            if(frame[0]=='D'&&n>1&&!write_all(1,frame+1,(size_t)n-1))break;
            if(frame[0]=='X'&&n==5){memcpy(&result,frame+1,4);break;}}
        if(p[0].revents&(POLLHUP|POLLERR|POLLNVAL))break;
        if(p[1].revents&POLLIN){ssize_t n=read(0,frame+1,FRAME_SIZE);if(n<=0)break;frame[0]='I';
            if(send(connection,frame,(size_t)n+1,MSG_NOSIGNAL)<0)break;}
        if(p[1].revents&(POLLHUP|POLLERR|POLLNVAL))break;
    }
    close(connection);if(has_tty)tcsetattr(0,TCSANOW,&original);return result;
}
static void serve_output(int server,int master,int *client,int notify){
    struct pollfd p[4]={{.fd=notify,.events=POLLIN},{.fd=server,.events=POLLIN},
        {.fd=master,.events=(((*client<0||pending_size==0)?POLLIN:0)|(input_size?POLLOUT:0))},
        {.fd=*client,.events=(input_size?0:POLLIN)|(pending_size?POLLOUT:0)}};
    poll(p,4,200);
    if(notify>=0&&p[0].revents){char events[8192];while(read(notify,events,sizeof events)>0){}}
    if(p[1].revents&POLLIN){int next=accept4(server,NULL,NULL,SOCK_CLOEXEC|SOCK_NONBLOCK);
        if(next>=0){struct ucred peer;socklen_t length=sizeof peer;
            if(getsockopt(next,SOL_SOCKET,SO_PEERCRED,&peer,&length)||(peer.uid!=0&&peer.uid!=app_uid))close(next);
            else {if(*client>=0)close(*client);*client=next;
                memcpy(pending,history,history_size);pending_size=history_size;pending_pos=0;}}}
    if(p[3].fd==*client&&*client>=0){
        if(p[3].revents&POLLIN){unsigned char frame[FRAME_SIZE+1];ssize_t n=recv(*client,frame,sizeof frame,0);
            if(n<=0){close(*client);*client=-1;pending_pos=pending_size=0;}
            else if(frame[0]=='I'&&n>1){memcpy(input_bytes,frame+1,(size_t)n-1);input_size=(size_t)n-1;input_pos=0;}
            else if(frame[0]=='R'&&n==(ssize_t)(1+sizeof(struct winsize))){struct winsize size;memcpy(&size,frame+1,sizeof size);ioctl(master,TIOCSWINSZ,&size);}}
        if(*client>=0&&p[3].revents&(POLLHUP|POLLERR|POLLNVAL)){close(*client);*client=-1;pending_pos=pending_size=0;}}
    if(*client>=0&&pending_size&&!flush_output(*client)){close(*client);*client=-1;pending_pos=pending_size=0;}
    if(input_size){ssize_t n=write(master,input_bytes+input_pos,input_size-input_pos);
        if(n>0)input_pos+=(size_t)n;if(input_pos==input_size)input_pos=input_size=0;}
    if(p[2].revents&POLLIN&&(*client<0||pending_size==0)){
        unsigned char bytes[FRAME_SIZE];ssize_t n=read(master,bytes,sizeof bytes);
        if(n>0){remember_output(bytes,(size_t)n);if(*client>=0){memcpy(pending,bytes,(size_t)n);pending_size=(size_t)n;pending_pos=0;}}}
}
static int proc_info(pid_t pid, Proc *out) {
    char name[64], line[4096]; snprintf(name,sizeof name,"/proc/%d/stat",pid);
    FILE *f=fopen(name,"re"); if(!f) return 0;
    if(!fgets(line,sizeof line,f)){fclose(f);return 0;} fclose(f);
    char *p=strrchr(line,')'); if(!p) return 0; p+=2;
    char *save=NULL,*t=strtok_r(p," ",&save); int field=3;
    memset(out,0,sizeof *out); out->pid=pid;
    while(t){if(field==3)out->state=*t; if(field==4)out->parent=atoi(t);
        if(field==22){out->start=strtoull(t,NULL,10);break;}
        t=strtok_r(NULL," ",&save);field++;}
    return out->start!=0;
}
static int same_process(Proc p){Proc now;return proc_info(p.pid,&now)&&now.start==p.start&&now.state!='Z';}
static int descendants(Proc **result) {
    DIR *d=opendir("/proc"); if(!d)return -1;
    size_t size=0,cap=256; Proc *all=malloc(cap*sizeof *all); struct dirent *e;
    if(!all){closedir(d);return -1;}
    while((e=readdir(d))){char *end;long pid=strtol(e->d_name,&end,10);
        if(*end||pid<=1||pid==getpid())continue;
        Proc p;if(!proc_info((pid_t)pid,&p))continue;
        if(size==cap){cap*=2;Proc *next=realloc(all,cap*sizeof *all);if(!next){free(all);closedir(d);return -1;}all=next;}
        all[size++]=p;}
    closedir(d);
    unsigned char *owned=calloc(size,1);if(!owned){free(all);return -1;}
    int changed;do {changed=0;for(size_t i=0;i<size;i++)if(!owned[i]){
        if(all[i].parent==getpid()){owned[i]=1;changed=1;continue;}
        for(size_t j=0;j<size;j++)if(owned[j]&&all[i].parent==all[j].pid){owned[i]=1;changed=1;break;}
    }}while(changed);
    int n=0;for(size_t i=0;i<size;i++)if(owned[i])all[n++]=all[i];free(owned);*result=all;return n;
}
static int signal_owned(int sig){Proc *ps=NULL;int n=descendants(&ps);if(n<0)return -1;
    for(int i=n-1;i>=0;i--)if(same_process(ps[i]))kill(ps[i].pid,sig);free(ps);return n;}
static void reap(void){while(waitpid(-1,NULL,WNOHANG)>0){}}
/* Only exited direct/adopted children are collected. Bash still owns its live
 * jobs; its final status must not be discarded by the general cleanup reaper. */
static int reap_running(pid_t worker,int *result){
    int worker_ended=0;
    while(1){
        int status=0;pid_t ended=waitpid(-1,&status,WNOHANG);
        if(ended>0){
            if(ended==worker){
                *result=WIFEXITED(status)?WEXITSTATUS(status):128+WTERMSIG(status);
                worker_ended=1;
            }
            continue;
        }
        if(ended==0)return worker_ended;
        if(errno==EINTR)continue;
        return worker_ended?1:-1;
    }
}
static int cleanup(void){
    for(int i=0;i<6;i++){if(signal_owned(SIGTERM)<0)return 0;reap();usleep(100000);}
    for(int i=0;i<20;i++){int n=signal_owned(SIGKILL);if(n<0)return 0;reap();if(n==0)return 1;usleep(50000);}
    return 0;
}
static void handle(int sig){(void)sig;stopping=1;}
static int command_stop(void){char name[4096],value[16]={0};snprintf(name,sizeof name,"%s/command",control_dir);
    int f=open(name,O_RDONLY|O_NOFOLLOW|O_CLOEXEC);if(f<0)return 0;ssize_t n=read(f,value,sizeof value-1);close(f);
    return n>=4&&!memcmp(value,"STOP",4);}
static int state(const char *value,int code){char name[4096],tmp[4096];
    snprintf(name,sizeof name,"%s/state",control_dir);snprintf(tmp,sizeof tmp,"%s/state.new",control_dir);
    int fd=open(tmp,O_WRONLY|O_CREAT|O_TRUNC|O_NOFOLLOW|O_CLOEXEC,0600);if(fd<0)return 0;
    fchown(fd,app_uid,(gid_t)app_uid);Proc me;proc_info(getpid(),&me);
    int written=dprintf(fd,"%s\n%d\n%llu\n%d\n",value,getpid(),me.start,code);close(fd);return written>0&&rename(tmp,name)==0;
}
int main(int argc,char **argv){
    if(argc<2)return 64;
    control_dir=getenv("DN_CONTROL_DIR");const char *uid=getenv("DN_APP_UID"),*mode=getenv("DN_MODE");
    const char *owner=getenv("DN_OWNER_PID"),*birth=getenv("DN_OWNER_START");
    if(!control_dir||!uid||!owner||!birth||getuid()!=0)return 77;
    app_uid=(uid_t)strtoul(uid,NULL,10);
    struct stat st;if(stat(control_dir,&st)||!S_ISDIR(st.st_mode)||st.st_uid!=app_uid)return 77;
    Proc owner_info={.pid=atoi(owner),.start=strtoull(birth,NULL,10)};
    if(!strcmp(argv[1],"--attach"))return attach_output(owner_info);
    int background=mode&&!strcmp(mode,"background");
    int launched[2]={-1,-1};
    if(background){if(pipe2(launched,O_CLOEXEC))return 71;pid_t daemon=fork();if(daemon<0)return 71;
        if(daemon>0){close(launched[1]);char ack;int ok=read(launched[0],&ack,1)==1;close(launched[0]);
            return ok?attach_output(owner_info):71;}
        close(launched[0]);
        if(setsid()<0)return 71;int null=open("/dev/null",O_RDWR);
        if(null<0)return 71;dup2(null,0);dup2(null,1);dup2(null,2);if(null>2)close(null);}
    if(prctl(PR_SET_CHILD_SUBREAPER,1,0,0,0))return 71;
    signal(SIGINT,SIG_IGN);signal(SIGQUIT,SIG_IGN);signal(SIGTTOU,SIG_IGN);signal(SIGTTIN,SIG_IGN);
    signal(SIGHUP,handle);signal(SIGTERM,handle);
    signal(SIGPIPE,SIG_IGN);
    int master=-1,server=-1,client=-1;char slave_name[128]={0};
    if(background){server=listen_output();master=posix_openpt(O_RDWR|O_NOCTTY|O_CLOEXEC|O_NONBLOCK);
        if(server<0||master<0||grantpt(master)||unlockpt(master)||ptsname_r(master,slave_name,sizeof slave_name)){
            state("FAILED",71);return 71;}}
    int ready[2];if(pipe2(ready,O_CLOEXEC)){state("FAILED",71);return 71;}
    pid_t worker=fork();if(worker<0){state("FAILED",71);return 71;}
    if(worker==0){
        if(background){close(server);close(master);close(launched[1]);
            if(setsid()<0)_exit(71);int slave=open(slave_name,O_RDWR|O_NOCTTY);
            if(slave<0||ioctl(slave,TIOCSCTTY,0))_exit(71);
            dup2(slave,0);dup2(slave,1);dup2(slave,2);if(slave>2)close(slave);tcsetpgrp(0,getpid());}
        else setpgid(0,0);
        signal(SIGINT,SIG_DFL);signal(SIGQUIT,SIG_DFL);signal(SIGTTOU,SIG_DFL);signal(SIGTTIN,SIG_DFL);
        signal(SIGHUP,SIG_DFL);signal(SIGTERM,SIG_DFL);close(ready[1]);char go;
        if(read(ready[0],&go,1)!=1)_exit(71);close(ready[0]);execv(argv[1],argv+1);_exit(126);}
    if(!background){setpgid(worker,worker);if(isatty(0))tcsetpgrp(0,worker);}
    close(ready[0]);if(write(ready[1],"1",1)!=1){kill(worker,SIGKILL);return 71;}close(ready[1]);
    if(!state("RUNNING",0)){cleanup();return 73;}
    if(background){if(write(launched[1],"1",1)!=1){cleanup();return 71;}close(launched[1]);}
    int notify=inotify_init1(IN_NONBLOCK|IN_CLOEXEC);
    if(notify>=0)inotify_add_watch(notify,control_dir,IN_CLOSE_WRITE|IN_DELETE_SELF|IN_MOVED_TO);
    int result=0;
    while(1){int ended=reap_running(worker,&result);if(ended>0)break;
        if(ended<0){result=125;break;}
        if(stopping||command_stop()||(!background&&!same_process(owner_info))){result=143;break;}
        if(background)serve_output(server,master,&client,notify);
        else {struct pollfd p={.fd=notify,.events=POLLIN};poll(&p,1,200);
            if(notify>=0&&p.revents){char events[8192];while(read(notify,events,sizeof events)>0){}}}
    }
    state("STOPPING",result);
    int clean=cleanup();if(notify>=0)close(notify);
    while(!clean){state("STOPPING",125);usleep(200000);clean=cleanup();}
    if(background){
        for(int i=0;i<12;i++)serve_output(server,master,&client,-1);
        state("FINISHED",result);
        if(client>=0){unsigned char done[5]={'X'};memcpy(done+1,&result,4);send(client,done,sizeof done,MSG_DONTWAIT|MSG_NOSIGNAL);close(client);}
        close(master);close(server);struct sockaddr_un address;if(socket_address(&address))unlink(address.sun_path);
    }
    state("FINISHED",result);return result;
}
